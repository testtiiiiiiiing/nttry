"""ISO-first project lifecycle. Source ISO is never overwritten."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid
from .plan import Plan, SETTINGS, unattended_xml


def editions(text):
    entries = []
    current = None
    for line in text.splitlines():
        match = re.match(r"\s*(Index|Name|Description|Architecture)\s*:\s*(.*)", line)
        if not match:
            continue
        key, value = match.groups()
        if key == "Index":
            current = {"index": int(value)}
            entries.append(current)
        elif current is not None:
            current[key.lower()] = value
    return entries


def inventory(text, primary, state="State"):
    entries, record = [], {}
    def flush():
        if primary in record:
            entries.append({"name": record[primary], "state": record.get(state, ""), "metadata": dict(record)})
        record.clear()
    for line in text.splitlines():
        if not line.strip():
            flush()
            continue
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        if key == primary and primary in record:
            flush()
        record[key] = value
    flush()
    return entries


class Project:
    def __init__(self, root, tools):
        self.root = Path(root).resolve()
        self.tools = tools
        self.media = self.root / "media"
        self.working = self.root / "working.wim"
        self.mount = self.root / "mount"
        self.state = {}

    def save(self):
        temporary = self.root / "project.json.tmp"
        temporary.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.root / "project.json")

    def log(self, message):
        self.tools.emit(message)

    def create(self, iso):
        source = self.tools.file(iso, {".iso"})
        if self.root.exists():
            raise ValueError("Usare una nuova cartella progetto; nessun file esistente sarà sovrascritto.")
        if self.root in source.parents:
            raise ValueError("La ISO originale deve rimanere fuori dal progetto.")
        required = max(source.stat().st_size * 4, 25 * 1024**3)
        parent = self.root.parent
        if not parent.is_dir():
            raise ValueError("La cartella padre del progetto deve esistere.")
        if shutil.disk_usage(parent).free < required:
            raise ValueError(f"Spazio insufficiente: servono almeno {required / 1024**3:.1f} GiB liberi.")
        self.root.mkdir()
        self.tools.log_file = self.root / "operations.log"
        self.state = {"version": 1, "source": str(source), "stage": "extracting", "completed": 0}
        self.save()
        self.tools.extract_iso(source, self.media)
        candidates = [self.media / "sources" / name for name in ("install.wim", "install.esd", "install.swm")]
        images = [p for p in candidates if p.is_file()]
        if len(images) != 1:
            raise ValueError("Supporto non supportato: serve una sola sorgente install.wim, install.esd o install.swm.")
        if not (self.media / "sources" / "boot.wim").is_file():
            raise ValueError("La ISO non contiene sources/boot.wim.")
        self.state["install"] = images[0].name
        self.state["editions"] = editions(self.tools.info(images[0]))
        if not self.state["editions"]:
            raise RuntimeError("DISM non ha restituito edizioni utilizzabili.")
        self.state["stage"] = "extracted"
        self.save()
        self.log("ISO estratta; originale conservato. Selezionare un’edizione.")
        return self.state["editions"]

    @classmethod
    def open(cls, root, tools):
        project = cls(root, tools)
        project.state = json.loads((project.root / "project.json").read_text(encoding="utf-8"))
        tools.log_file = project.root / "operations.log"
        if project.state.get("version") != 1 or project.state.get("stage") not in {"extracted", "mounted", "committed", "exported"}:
            raise ValueError("Progetto incompleto: consultare il registro e ripartire in una nuova cartella.")
        if project.state["stage"] == "mounted":
            text = tools.dism("/Get-MountedWimInfo")
            blocks = re.split(r"(?=Mount Dir\s*:)" , text)
            found = False
            for block in blocks:
                mount = re.search(r"Mount Dir\s*:\s*(.+)", block)
                image = re.search(r"Image File\s*:\s*(.+)", block)
                status = re.search(r"Status\s*:\s*(.+)", block)
                if (mount and image and status and Path(mount[1].strip()).resolve() == project.mount
                        and Path(image[1].strip()).resolve() == project.working and status[1].strip() == "Ok"):
                    found = True
            if not found:
                raise RuntimeError("Montaggio non integro o assente. Recuperare prima l’immagine con DISM; il progetto non sarà modificato.")
            tools.mount = project.mount
        return project

    def load_edition(self, index):
        if self.state.get("stage") != "extracted":
            raise ValueError("L’edizione può essere scelta solo dopo l’estrazione.")
        if int(index) not in [e["index"] for e in self.state["editions"]]:
            raise ValueError("Edizione non presente nel supporto.")
        source = self.media / "sources" / self.state["install"]
        detail = self.tools.image_detail(source, index)
        arch = re.search(r"Architecture\s*:\s*(\S+)", detail)
        architecture = {"x64": "amd64", "amd64": "amd64", "x86": "x86", "arm64": "arm64"}.get(arch[1].lower() if arch else "")
        if not architecture:
            raise ValueError("Impossibile determinare l’architettura dell’edizione.")
        self.tools.export(source, index, self.working)
        self.tools.mount_image(self.working, 1, self.mount)
        self.state.update(stage="mounted", index=int(index), architecture=architecture)
        self.save()
        self.log("Edizione montata dalla copia di lavoro; la ISO finale conterrà questa sola edizione.")

    def list_items(self, category):
        command, primary, state = {
            "features": ("/Get-Features", "Feature Name", "State"),
            "packages": ("/Get-Packages", "Package Identity", "State"),
            "appx": ("/Get-ProvisionedAppxPackages", "PackageName", "DisplayName"),
            "capabilities": ("/Get-Capabilities", "Capability Identity", "State"),
            "drivers": ("/Get-Drivers", "Published Name", "Original File Name"),
        }[category]
        return inventory(self.tools.service(command), primary, state)

    def apply_operation(self, op):
        kind, value = op["kind"], op["value"]
        if kind == "driver":
            self.tools.add_driver(value)
        elif kind == "update":
            self.tools.add_package(value)
        elif kind.startswith("feature_"):
            if kind == "feature_remove":
                self.tools.service("/Disable-Feature", f"/FeatureName:{value}", "/Remove")
            else:
                self.tools.feature(value, kind == "feature_enable")
        elif kind == "package_remove":
            self.tools.remove_package(value)
        elif kind == "appx_remove":
            self.tools.service("/Remove-ProvisionedAppxPackage", f"/PackageName:{value}")
        elif kind == "capability_remove":
            self.tools.service("/Remove-Capability", f"/CapabilityName:{value}")
        elif kind == "driver_remove":
            self.tools.service("/Remove-Driver", f"/Driver:{value}")
        elif kind == "setting":
            hive, key, name, data = SETTINGS[value]
            self.tools.offline_registry(hive, key, name, data)
        elif kind == "service":
            self.tools.configure_service(value, op["start"])
        elif kind == "post_setup":
            self.tools.add_post_setup(value, op.get("args", ""))
        elif kind == "cleanup":
            self.tools.cleanup()
        elif kind == "registry":
            self.tools.offline_registry(op["hive"], value, op["name"], op["data"], op["type"])
        elif kind == "scheduled_task":
            action = op["action"]
            command = f'schtasks.exe /Delete /TN "{value}" /F' if action == "delete" else f'schtasks.exe /Change /TN "{value}" /{action.upper()}'
            self.tools.setup_command(command)
        elif kind == "power_plan":
            self.tools.add_power_plan(value)

    def apply(self, plan):
        if self.state.get("stage") != "mounted":
            raise ValueError("Caricare un’edizione prima di applicare modifiche.")
        data = plan.to_dict()
        digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        if self.state.get("plan_hash") and self.state["plan_hash"] != digest:
            raise ValueError("Il piano è già iniziato. Ricaricare il preset salvato nel progetto o scartare e ricominciare.")
        # Validate all local inputs before any servicing command runs.
        for op in plan.operations:
            if op["kind"] in {"update", "post_setup"}:
                self.tools.file(op["value"], {".cab", ".msu"} if op["kind"] == "update" else {".cmd", ".bat", ".exe", ".msi"})
            if op["kind"] == "driver":
                path = Path(op["value"])
                if not path.is_dir() or not any(p.suffix.lower() == ".inf" for p in path.rglob("*")):
                    raise ValueError("Cartella driver INF non valida.")
            if op["kind"] == "power_plan":
                self.tools.file(op["value"], {".pow"})
        if plan.unattended:
            unattended_xml(plan.unattended, self.state["architecture"])
            if (self.media / "autounattend.xml").exists() and not self.state.get("unattended_written"):
                raise ValueError("Il supporto contiene già autounattend.xml: non sarà sovrascritto.")
        plan.save(self.root / "applied-preset.json")
        self.state["plan_hash"] = digest
        self.save()
        for i, op in enumerate(plan.operations):
            if i < self.state["completed"]:
                continue
            self.log(f"Operazione {i + 1}/{len(plan.operations)}: {op['kind']} — {op['value']}")
            self.apply_operation(op)
            self.state["completed"] = i + 1
            self.save()
        if plan.unattended:
            (self.media / "autounattend.xml").write_bytes(unattended_xml(plan.unattended, self.state["architecture"]))
            self.state["unattended_written"] = True
            self.save()
        self.tools.unmount(True)
        self.state["stage"] = "committed"
        self.save()
        self.log("Personalizzazioni salvate e immagine smontata.")

    def build(self, destination, oscdimg):
        if self.state.get("stage") not in {"committed", "exported"}:
            raise ValueError("Applicare il piano e smontare l’immagine prima di creare la ISO.")
        destination = Path(destination).resolve()
        if destination.exists() or self.root == destination.parent or self.root in destination.parents:
            raise ValueError("La ISO deve essere un nuovo file fuori dalla cartella progetto.")
        if destination.suffix.lower() != ".iso":
            raise ValueError("Specificare un file .iso.")
        original = self.media / "sources" / self.state["install"]
        backup = self.root / "original-install" / self.state["install"]
        backup.parent.mkdir(exist_ok=True)
        if original.exists() and not backup.exists():
            shutil.move(original, backup)
        if self.state["install"] == "install.swm":
            for chunk in (self.media / "sources").glob("install*.swm"):
                if (backup.parent / chunk.name).exists():
                    raise ValueError("Backup SWM già presente: verificare lo stato del progetto prima di procedere.")
                shutil.move(chunk, backup.parent / chunk.name)
        target = self.media / "sources" / "install.wim"
        if not target.exists():
            temporary = target.with_name("install.export." + uuid.uuid4().hex + ".wim")
            try:
                self.tools.export(self.working, 1, temporary)
                if not temporary.is_file() or not temporary.stat().st_size:
                    raise RuntimeError("Esportazione ottimizzata WIM non riuscita.")
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        temporary_iso = destination.with_name(destination.stem + "." + uuid.uuid4().hex + ".partial.iso")
        try:
            self.tools.build_iso(self.media, temporary_iso, oscdimg)
            if not temporary_iso.is_file() or temporary_iso.stat().st_size == 0:
                raise RuntimeError("oscdimg non ha generato una ISO non vuota.")
            if destination.exists():
                raise ValueError("La ISO destinazione è stata creata da un altro processo; non verrà sovrascritta.")
            temporary_iso.rename(destination)
        finally:
            temporary_iso.unlink(missing_ok=True)
        self.state.update(stage="exported", output=str(destination))
        self.save()
        self.log(f"ISO creata: {destination}")

    def discard(self):
        if self.state.get("stage") != "mounted":
            raise ValueError("Nessuna immagine del progetto montata.")
        self.tools.unmount(False)
        self.working.unlink()
        self.state.update(stage="extracted", completed=0)
        self.state.pop("plan_hash", None)
        if self.state.pop("unattended_written", False):
            (self.media / "autounattend.xml").unlink(missing_ok=True)
        self.save()
        self.log("Modifiche scartate. Selezionare nuovamente un’edizione.")
