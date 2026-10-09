from pathlib import Path
import ctypes
import os
import subprocess


class ImageTools:
    def __init__(self, emit=print, runner=subprocess.run):
        self.emit = emit
        self.runner = runner
        self.mount = None

    def run(self, args):
        self.emit(subprocess.list2cmdline([str(a) for a in args]))
        result = self.runner([str(a) for a in args], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, errors="replace")
        self.emit(result.stdout or "")
        if result.returncode not in (0, 3010):
            raise RuntimeError(f"Comando fallito, codice {result.returncode}. Consultare il registro.")
        if result.returncode == 3010:
            self.emit("Operazione riuscita; riavvio richiesto da Windows.")
        return result.stdout

    def dism(self, *args):
        if os.name != "nt":
            raise RuntimeError("DISM richiede Windows. Questa macchina non può modificare immagini Windows.")
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "dism.exe"
        return self.run([executable, "/English", *args])

    @staticmethod
    def file(value, suffixes):
        path = Path(value).resolve()
        if not path.is_file() or path.suffix.lower() not in suffixes:
            raise ValueError(f"Selezionare un file esistente: {', '.join(suffixes)}")
        return path

    def info(self, image):
        return self.dism("/Get-WimInfo", f"/WimFile:{self.file(image, {'.wim', '.esd'})}")

    def mount_image(self, image, index, directory):
        if self.mount:
            raise ValueError("Smontare prima l’immagine corrente.")
        image = self.file(image, {".wim"})
        index = int(index)
        if index < 1:
            raise ValueError("L’indice deve essere maggiore di zero.")
        directory = Path(directory).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        if any(directory.iterdir()):
            raise ValueError("La cartella di montaggio deve essere vuota.")
        self.dism("/Mount-Image", f"/ImageFile:{image}", f"/Index:{index}", f"/MountDir:{directory}", "/CheckIntegrity")
        self.mount = directory

    def service(self, *args):
        if not self.mount:
            raise ValueError("Montare prima un’immagine WIM.")
        return self.dism(f"/Image:{self.mount}", *args)

    def add_driver(self, directory):
        path = Path(directory).resolve()
        if not path.is_dir() or not any(path.rglob("*.inf")):
            raise ValueError("La cartella deve contenere driver INF.")
        self.service("/Add-Driver", f"/Driver:{path}", "/Recurse")

    def add_package(self, package):
        self.service("/Add-Package", f"/PackagePath:{self.file(package, {'.cab', '.msu'})}")

    def feature(self, name, enabled):
        if not name.strip() or any(c in name for c in "\r\n"):
            raise ValueError("Specificare il nome esatto della funzionalità DISM.")
        self.service("/Enable-Feature" if enabled else "/Disable-Feature", f"/FeatureName:{name.strip()}")

    def remove_package(self, name):
        if not name.strip() or any(c in name for c in "\r\n"):
            raise ValueError("Specificare l’identità completa del pacchetto.")
        self.service("/Remove-Package", f"/PackageName:{name.strip()}")

    def unmount(self, commit):
        if not self.mount:
            raise ValueError("Nessuna immagine montata da questa sessione.")
        self.dism("/Unmount-Image", f"/MountDir:{self.mount}", "/Commit" if commit else "/Discard")
        self.mount = None

    def export(self, image, index, destination):
        image = self.file(image, {".wim", ".esd"})
        destination = Path(destination).resolve()
        if destination.exists() or destination.suffix.lower() != ".wim":
            raise ValueError("La destinazione deve essere un nuovo file .wim.")
        index = int(index)
        if index < 1:
            raise ValueError("Indice non valido.")
        self.dism("/Export-Image", f"/SourceImageFile:{image}", f"/SourceIndex:{index}",
                  f"/DestinationImageFile:{destination}", "/Compress:max", "/CheckIntegrity")

    def extract_iso(self, image, destination):
        image = self.file(image, {".iso"})
        destination = Path(destination).resolve()
        if destination.exists():
            raise ValueError("Usare una nuova cartella di destinazione.")
        if os.name != "nt":
            raise RuntimeError("L’estrazione ISO richiede Windows PowerShell.")
        # Environment variables carry paths without interpolating user input into code.
        script = "$ErrorActionPreference='Stop'; $disk=Mount-DiskImage -ImagePath $env:WINIMAGE_ISO -PassThru; try { $vol=$disk | Get-Volume; if (!$vol.DriveLetter) { throw 'ISO senza lettera di unità' }; New-Item -ItemType Directory -Path $env:WINIMAGE_DEST | Out-Null; Copy-Item -Path ($vol.DriveLetter + ':\\*') -Destination $env:WINIMAGE_DEST -Recurse -Force; Get-ChildItem -LiteralPath $env:WINIMAGE_DEST -Recurse -File | ForEach-Object { $_.IsReadOnly=$false } } finally { Dismount-DiskImage -ImagePath $env:WINIMAGE_ISO | Out-Null }"
        env = os.environ.copy()
        env.update(WINIMAGE_ISO=str(image), WINIMAGE_DEST=str(destination))
        result = self.runner(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                             env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, errors="replace")
        self.emit(result.stdout or "")
        if result.returncode:
            raise RuntimeError("Estrazione ISO fallita; consultare il registro.")

    def build_iso(self, source, destination, oscdimg):
        source = Path(source).resolve()
        destination = Path(destination).resolve()
        tool = self.file(oscdimg, {".exe"})
        bios = source / "boot" / "etfsboot.com"
        uefi = source / "efi" / "microsoft" / "boot" / "efisys.bin"
        if not bios.is_file() or not uefi.is_file() or not (source / "sources" / "boot.wim").is_file():
            raise ValueError("La cartella deve contenere un supporto Windows completo, con avvio BIOS e UEFI.")
        if destination.exists() or destination.suffix.lower() != ".iso" or source in destination.parents:
            raise ValueError("Scegliere un nuovo file .iso fuori dalla cartella sorgente.")
        self.run([tool, "-m", "-o", "-u2", "-udfver102", f"-bootdata:2#p0,e,b{bios}#pEF,e,b{uefi}", source, destination])


def is_admin():
    return os.name == "nt" and bool(ctypes.windll.shell32.IsUserAnAdmin())
