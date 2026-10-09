"""Unattended invocation of the same ISO project engine used by the GUI."""
import argparse
import json
from pathlib import Path
import sys
from .backend import ImageTools, is_admin
from .plan import Plan, destructive_setup
from .project import Project


def main(argv=None):
    parser = argparse.ArgumentParser(description="WinImage Studio — ISO Windows personalizzate")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-preset", help="Valida un preset, anche senza Windows")
    validate.add_argument("preset")
    download = sub.add_parser('download-updates', help='Scarica manifest Microsoft con cache e verifica SHA-256')
    download.add_argument('--manifest', required=True)
    download.add_argument('--cache', required=True)
    download.add_argument('--workers', type=int, default=3)
    inspect = sub.add_parser("inspect", help="Estrai ISO in un nuovo progetto ed elenca edizioni")
    inspect.add_argument("--iso", required=True)
    inspect.add_argument("--project", required=True)
    inspect.add_argument("--wimlib", default="", help="wimlib-imagex.exe, necessario solo per sorgenti SWM")
    run = sub.add_parser("run", help="ISO → personalizzazione → nuova ISO; una o più edizioni in ISO separate")
    run.add_argument("--iso", required=True)
    run.add_argument("--project", required=True, help="Nuova cartella progetto, o prefisso per batch")
    run.add_argument("--indices", default="1", help="Indici separati da virgola, es. 1,6")
    run.add_argument("--preset", required=True)
    run.add_argument("--output", required=True, help="ISO destinazione; in batch vengono aggiunti gli indici")
    run.add_argument("--oscdimg", default=ImageTools.find_oscdimg())
    run.add_argument("--wimlib", default="")
    run.add_argument("--confirm", action="store_true", help="Autorizza le operazioni del preset dopo averle revisionate")
    run.add_argument("--confirm-wipe-disk", action="store_true", help="Autorizza un answer file che cancella dischi DURANTE Setup")
    resume = sub.add_parser("resume", help="Riprendi progetto montato/salvato")
    resume.add_argument("--project", required=True)
    resume.add_argument("--preset")
    resume.add_argument("--index", type=int, default=1, help="Edizione da caricare se il progetto è ancora solo estratto")
    resume.add_argument("--wimlib", default="")
    resume.add_argument("--output", required=True)
    resume.add_argument("--oscdimg", default=ImageTools.find_oscdimg())
    resume.add_argument("--confirm", action="store_true")
    resume.add_argument("--confirm-wipe-disk", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-preset":
            print(json.dumps(Plan.load(args.preset).to_dict(), ensure_ascii=False, indent=2))
            return 0
        if args.command == 'download-updates':
            from .updates import download_updates
            print(json.dumps(download_updates(args.manifest, args.cache, workers=args.workers), indent=2))
            return 0
        if not is_admin():
            raise RuntimeError("Richiede Windows e un terminale amministratore.")
        tools = ImageTools()
        if getattr(args, 'wimlib', ''):
            tools.wimlib = args.wimlib
        if args.command == "inspect":
            project = Project(args.project, tools)
            print(json.dumps(project.create(args.iso), ensure_ascii=False, indent=2))
            return 0
        if not args.confirm:
            raise ValueError("Revisionare il preset, poi fornire --confirm per applicarlo.")
        tools.file(args.oscdimg, {".exe"})
        if args.command == "resume":
            project = Project.open(args.project, tools)
            if project.state["stage"] == "extracted":
                if not args.preset:
                    raise ValueError("Un progetto appena estratto richiede --preset per la personalizzazione.")
                Plan.load(args.preset)
                project.load_edition(args.index)
            if project.state["stage"] == "mounted":
                plan = Plan.load(args.preset or project.root / "applied-preset.json")
                if destructive_setup(plan.unattended) and not args.confirm_wipe_disk:
                    raise ValueError("Il setup cancellerà dischi: richiede --confirm-wipe-disk.")
                project.apply(plan)
            project.build(args.output, args.oscdimg)
            return 0
        indices = [int(value) for value in args.indices.split(",")]
        if not indices or len(indices) > 100 or any(i < 1 for i in indices) or len(set(indices)) != len(indices):
            raise ValueError("Indici edizione non validi o duplicati.")
        plan = Plan.load(args.preset)
        if destructive_setup(plan.unattended) and not args.confirm_wipe_disk:
            raise ValueError("Il setup cancellerà dischi: richiede --confirm-wipe-disk.")
        output = Path(args.output)
        if output.suffix.lower() != ".iso":
            raise ValueError("La destinazione deve terminare con .iso.")
        projects = [Path(args.project) if len(indices) == 1 else Path(f"{args.project}-{index}") for index in indices]
        outputs = [output if len(indices) == 1 else output.with_name(f"{output.stem}-{index}.iso") for index in indices]
        if any(path.exists() for path in projects + outputs):
            raise ValueError("Progetto o ISO di destinazione già esistente; scegliere nuovi percorsi.")
        for index, root, destination in zip(indices, projects, outputs):
            project = Project(root, tools)
            project.create(args.iso)
            project.load_edition(index)
            project.apply(plan)
            project.build(destination, args.oscdimg)
        return 0
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(f"ERRORE: {exc}", file=sys.stderr)
        print("Se un’immagine è ancora montata, consultare project.json e operations.log prima di recuperarla.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
