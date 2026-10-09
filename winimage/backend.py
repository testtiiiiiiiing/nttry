from pathlib import Path
import ctypes
import os
import subprocess
import re
import shutil
import uuid
import tempfile
import xml.etree.ElementTree as ET


class ImageTools:
    def __init__(self, emit=print, runner=None):
        self.callback = emit
        self.log_file = None
        self.runner = runner
        self.mount = None
        self.wimlib = shutil.which("wimlib-imagex.exe") or shutil.which("wimlib-imagex") or ""

    def emit(self, message):
        self.callback(message)
        if self.log_file:
            with Path(self.log_file).open('a', encoding='utf-8') as log:
                log.write(str(message) + '\n')

    def run(self, args):
        logged_args = [str(a) for a in args]
        if logged_args and Path(logged_args[0]).name.lower() == 'reg.exe' and '/d' in logged_args:
            logged_args[logged_args.index('/d') + 1] = '[valore omesso]'
        self.emit(subprocess.list2cmdline(logged_args))
        argv = [str(a) for a in args]
        if self.runner:
            result = self.runner(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
            output, code = result.stdout or "", result.returncode
            self.emit(output)
        else:
            process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, errors="replace", creationflags=0x08000000 if os.name == "nt" else 0)
            lines = []
            for line in process.stdout:
                lines.append(line)
                self.emit(line.rstrip())
            code = process.wait()
            output = "".join(lines)
        if code not in (0, 3010):
            raise RuntimeError(f"Comando fallito, codice {code}. Consultare il registro.")
        if code == 3010:
            self.emit("Operazione riuscita; riavvio richiesto da Windows.")
        return output

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
        path = self.file(image, {'.wim', '.esd', '.swm'})
        if path.suffix.lower() == '.swm':
            rows = self.split_info(path)
            return '\n'.join(f"Index : {row['index']}\nName : {row['name']}\nArchitecture : {row['architecture']}" for row in rows)
        return self.dism("/Get-WimInfo", f"/WimFile:{path}")

    def image_detail(self, image, index):
        path = self.file(image, {'.wim', '.esd', '.swm'})
        if path.suffix.lower() == '.swm':
            rows = [row for row in self.split_info(path) if row['index'] == int(index)]
            if not rows:
                raise ValueError('Indice SWM non presente.')
            return f"Architecture : {rows[0]['architecture']}"
        return self.dism('/Get-WimInfo', f'/WimFile:{path}', f'/Index:{int(index)}')

    def split_info(self, image):
        if not self.wimlib:
            raise ValueError('Le immagini SWM richiedono wimlib-imagex.exe. Selezionare lo strumento prima di estrarre.')
        with tempfile.TemporaryDirectory(prefix='winimage-xml-') as directory:
            xml = Path(directory) / 'image.xml'
            self.run([self.wimlib, 'info', image, f'--extract-xml={xml}'])
            root = ET.parse(xml).getroot()
            result = []
            for item in root.findall('IMAGE'):
                architecture = {'0': 'x86', '9': 'x64', '12': 'arm64'}.get(item.findtext('WINDOWS/ARCH'), 'unknown')
                result.append({'index': int(item.attrib['INDEX']), 'name': item.findtext('NAME') or 'Windows', 'architecture': architecture})
            return result

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
        if not path.is_dir() or not any(p.suffix.lower() == ".inf" for p in path.rglob("*")):
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
        image = self.file(image, {".wim", ".esd", ".swm"})
        destination = Path(destination).resolve()
        if destination.exists() or destination.suffix.lower() != ".wim":
            raise ValueError("La destinazione deve essere un nuovo file .wim.")
        index = int(index)
        if index < 1:
            raise ValueError("Indice non valido.")
        if image.suffix.lower() == '.swm':
            if not self.wimlib:
                raise ValueError('Esportazione SWM richiede wimlib-imagex.exe.')
            self.run([self.wimlib, 'export', image, index, destination, f'--ref={image.parent / "install*.swm"}', '--compress=LZX', '--check'])
            return
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
        script = "$ErrorActionPreference='Stop'; $disk=Get-DiskImage -ImagePath $env:WINIMAGE_ISO; $owned=!$disk.Attached; if ($owned) { $disk=Mount-DiskImage -ImagePath $env:WINIMAGE_ISO -PassThru }; try { $vol=$disk | Get-Volume; if (!$vol.DriveLetter) { throw 'ISO senza lettera di unità' }; New-Item -ItemType Directory -Path $env:WINIMAGE_DEST | Out-Null; Copy-Item -Path ($vol.DriveLetter + ':\\*') -Destination $env:WINIMAGE_DEST -Recurse -Force; Get-ChildItem -LiteralPath $env:WINIMAGE_DEST -Recurse -File | ForEach-Object { $_.IsReadOnly=$false } } finally { if ($owned) { Dismount-DiskImage -ImagePath $env:WINIMAGE_ISO | Out-Null } }"
        env = os.environ.copy()
        env.update(WINIMAGE_ISO=str(image), WINIMAGE_DEST=str(destination))
        result = (self.runner or subprocess.run)(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
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

    def offline_registry(self, hive, key, name, value, value_type="REG_DWORD"):
        if not self.mount:
            raise ValueError("Nessuna immagine offline montata.")
        files = {"SOFTWARE": self.mount / "Windows/System32/config/SOFTWARE",
                 "SYSTEM": self.mount / "Windows/System32/config/SYSTEM",
                 "DEFAULTUSER": self.mount / "Users/Default/NTUSER.DAT"}
        if hive not in files or not files[hive].is_file():
            raise ValueError("Hive offline assente o non supportato.")
        loaded = "HKLM\\WinImage_" + uuid.uuid4().hex
        self.run(["reg.exe", "load", loaded, files[hive]])
        try:
            if hive == "SYSTEM" and key.startswith("@CURRENT@"):
                output = self.run(["reg.exe", "query", loaded + r"\Select", "/v", "Default"])
                number = re.search(r"Default\s+REG_DWORD\s+(0x[0-9a-fA-F]+|\d+)", output)
                if not number:
                    raise RuntimeError("ControlSet di avvio non determinabile.")
                key = f"ControlSet{int(number[1], 0):03d}" + key[len("@CURRENT@") :]
            if hive == "SYSTEM" and "\\Services\\" in key:
                # Query first: never create a nonexistent service registry key.
                self.run(["reg.exe", "query", loaded + "\\" + key])
            self.run(["reg.exe", "add", loaded + "\\" + key, "/v", name, "/t", value_type, "/d", value, "/f"])
        finally:
            self.run(["reg.exe", "unload", loaded])

    def configure_service(self, name, start):
        self.offline_registry("SYSTEM", "@CURRENT@\\Services\\" + name, "Start", start)

    def setup_command(self, command):
        if not self.mount:
            raise ValueError("Nessuna immagine montata.")
        directory = self.mount / "Windows/Setup/Scripts"
        directory.mkdir(parents=True, exist_ok=True)
        setup = directory / "SetupComplete.cmd"
        if setup.exists() and "REM WinImage Studio managed" not in setup.read_text(encoding="utf-8", errors="replace"):
            raise ValueError("SetupComplete.cmd preesistente: non sarà modificato.")
        previous = setup.read_text(encoding="utf-8") if setup.exists() else "@echo off\nREM WinImage Studio managed\n"
        if command not in previous.splitlines():
            setup.write_bytes((previous + command + "\n").replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))

    def add_post_setup(self, source, args):
        path = self.file(source, {".exe", ".msi", ".cmd", ".bat"})
        if not self.mount:
            raise ValueError("Nessuna immagine montata.")
        # Stable content names permit a retry without adding a second script line.
        import hashlib
        with path.open("rb") as source_file:
            digest = hashlib.file_digest(source_file, "sha256").hexdigest()[:16]
        name = digest + path.suffix.lower()
        payload = self.mount / "Windows/Setup/Scripts/Payload"
        payload.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, payload / name)
        executable = f'"%WINDIR%\\Setup\\Scripts\\Payload\\{name}"'
        if path.suffix.lower() == ".msi":
            command = f"start /wait msiexec.exe /i {executable} /qn /norestart {args}"
        elif path.suffix.lower() in {".cmd", ".bat"}:
            command = f"call {executable} {args}"
        else:
            command = f'start /wait "" {executable} {args}'
        self.setup_command(command.strip())

    def cleanup(self):
        self.service("/Cleanup-Image", "/StartComponentCleanup")

    def add_power_plan(self, source):
        path = self.file(source, {".pow"})
        if not self.mount:
            raise ValueError("Nessuna immagine montata.")
        import hashlib
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        guid = str(uuid.UUID(digest[:32]))
        directory = self.mount / "Windows/Setup/Scripts/Payload"
        directory.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, directory / (guid + ".pow"))
        self.setup_command(f'powercfg.exe /import "%WINDIR%\\Setup\\Scripts\\Payload\\{guid}.pow" {guid}')
        self.setup_command(f"powercfg.exe /setactive {guid}")

    def export_host_drivers(self, destination):
        destination = Path(destination).resolve()
        if destination.exists():
            raise ValueError('Selezionare una nuova cartella per i driver di questo PC.')
        destination.mkdir(parents=True)
        self.dism('/Online', '/Export-Driver', f'/Destination:{destination}')
        return str(destination)

    @staticmethod
    def find_oscdimg():
        candidate = shutil.which("oscdimg.exe")
        if candidate:
            return candidate
        for base in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), os.environ.get("ProgramFiles", r"C:\Program Files")):
            path = Path(base) / "Windows Kits/10/Assessment and Deployment Kit/Deployment Tools/amd64/Oscdimg/oscdimg.exe"
            if path.is_file():
                return str(path)
        return ""


def is_admin():
    return os.name == "nt" and bool(ctypes.windll.shell32.IsUserAnAdmin())
