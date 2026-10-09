"""Portable, validated customization presets and unattended Setup XML."""
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

SETTINGS = {
    "disable_consumer_apps": ("SOFTWARE", r"Policies\Microsoft\Windows\CloudContent", "DisableWindowsConsumerFeatures", 1),
    "reduce_telemetry": ("SOFTWARE", r"Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", 0),
    "show_file_extensions": ("DEFAULTUSER", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "HideFileExt", 0),
    "show_hidden_files": ("DEFAULTUSER", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "Hidden", 1),
    "disable_bing_search": ("DEFAULTUSER", r"Software\Policies\Microsoft\Windows\Explorer", "DisableSearchBoxSuggestions", 1),
}
SETTING_LABELS = {
    "disable_consumer_apps": "Disabilita suggerimenti app consumer (edizioni supportate)",
    "reduce_telemetry": "Riduci telemetria (effetto dipendente dall’edizione)",
    "show_file_extensions": "Mostra estensioni per i nuovi utenti",
    "show_hidden_files": "Mostra file nascosti per i nuovi utenti",
    "disable_bing_search": "Disabilita suggerimenti web nella ricerca per i nuovi utenti",
}
KINDS = {"driver", "update", "feature_enable", "feature_disable", "feature_remove",
         "package_remove", "appx_remove", "capability_remove", "driver_remove", "setting", "service", "post_setup",
         "cleanup", "registry", "scheduled_task", "power_plan"}


def identity(value):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError("Nome mancante o contenente caratteri di controllo.")
    return value.strip()


@dataclass
class Plan:
    operations: list = field(default_factory=list)
    unattended: dict = field(default_factory=dict)

    def validate(self):
        if not isinstance(self.operations, list) or len(self.operations) > 1000:
            raise ValueError("Il preset deve contenere al massimo 1000 operazioni.")
        for op in self.operations:
            if not isinstance(op, dict) or op.get("kind") not in KINDS:
                raise ValueError("Operazione preset non supportata.")
            value = identity(op.get("value"))
            if op["kind"] == "setting" and value not in SETTINGS:
                raise ValueError("Impostazione non supportata.")
            if op["kind"] == "service":
                if not re.fullmatch(r"[A-Za-z0-9_.-]+", value) or op.get("start") not in (2, 3, 4):
                    raise ValueError("Nome servizio o modalità di avvio non valido.")
                if value.lower() in {"rpcss", "dcomlaunch", "plugplay", "trustedinstaller", "wuauserv"}:
                    raise ValueError("Questo servizio è protetto per mantenere l’immagine utilizzabile.")
            if op["kind"] == "driver_remove" and not re.fullmatch(r"oem\d+\.inf", value, re.I):
                raise ValueError("Si possono rimuovere solo driver di terze parti oemN.inf.")
            if op["kind"] == "package_remove" and re.search(r"ServicingStack|Foundation-Package", value, re.I):
                raise ValueError("Pacchetto di manutenzione essenziale protetto.")
            if op["kind"] == "post_setup":
                args = op.get("args", "")
                if not isinstance(args, str) or any(ord(c) < 32 for c in args) or any(c in args for c in '&|<>^%'):
                    raise ValueError("Argomenti post-installazione: usare solo opzioni semplici, senza operatori shell.")
            if op["kind"] == "registry":
                if op.get("hive") not in {"SOFTWARE", "SYSTEM", "DEFAULTUSER"} or op.get("type") not in {"REG_SZ", "REG_DWORD"}:
                    raise ValueError("Hive o tipo di registro non supportato.")
                identity(op.get("name"))
                if value.startswith("\\") or ".." in value or "/" in value:
                    raise ValueError("Usare una chiave relativa all’hive offline.")
                data = op.get("data")
                if not isinstance(data, str) or any(ord(c) < 32 for c in data):
                    raise ValueError("Dati del registro non validi.")
                if op["type"] == "REG_DWORD":
                    try:
                        number = int(data, 16 if data.lower().startswith("0x") else 10)
                    except ValueError:
                        raise ValueError("REG_DWORD richiede un numero decimale o 0x esadecimale.") from None
                    if not 0 <= number <= 0xffffffff:
                        raise ValueError("REG_DWORD fuori intervallo.")
            if op["kind"] == "scheduled_task":
                if op.get("action") not in {"enable", "disable", "delete"} or any(c in value for c in '\"&|<>^%'):
                    raise ValueError("Nome attività o azione non valido.")
        if not isinstance(self.unattended, dict) or set(self.unattended) - {"locale", "computer_name", "time_zone", "disk_id", "wipe_disk", "accept_eula", "xml_path"}:
            raise ValueError("Configurazione unattended non supportata.")
        if "xml_path" in self.unattended:
            if len(self.unattended) != 1:
                raise ValueError("Il file XML esterno non può essere combinato con il generatore.")
            identity(self.unattended["xml_path"])
            return self
        if self.unattended:
            locale = self.unattended.get("locale", "it-IT")
            name = self.unattended.get("computer_name", "WINIMAGE")
            identity(self.unattended.get("time_zone", "W. Europe Standard Time"))
            if not isinstance(locale, str) or not re.fullmatch(r"[a-z]{2,3}-[A-Z]{2}", locale):
                raise ValueError("Locale non valido (esempio it-IT).")
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,15}", name) or name.isdigit():
                raise ValueError("Nome computer: 1–15 lettere, numeri o trattini; non solo numeri.")
            if "disk_id" in self.unattended:
                disk_id = self.unattended["disk_id"]
                if type(disk_id) is not int or not 0 <= disk_id < 32 or self.unattended.get("wipe_disk") is not True:
                    raise ValueError("Partizionamento: serve un disco esplicito 0–31 e wipe_disk=true.")
            elif self.unattended.get("wipe_disk"):
                raise ValueError("Indicare il disco da partizionare.")
            if "accept_eula" in self.unattended and type(self.unattended["accept_eula"]) is not bool:
                raise ValueError("accept_eula deve essere un booleano.")
        return self

    def to_dict(self):
        self.validate()
        config = self.unattended
        if config and "xml_path" not in config:
            config = {"locale": "it-IT", "computer_name": "WINIMAGE", "time_zone": "W. Europe Standard Time", "accept_eula": False, **config}
        return {"version": 1, "operations": self.operations, "unattended": config}

    def save(self, path):
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("Versione preset non supportata.")
        return cls(data.get("operations", []), data.get("unattended", {})).validate()


def unattended_xml(config, architecture="amd64"):
    Plan(unattended=config).validate()
    if "xml_path" in config:
        path = Path(config["xml_path"])
        if not path.is_file() or path.stat().st_size > 2 * 1024**2:
            raise ValueError("XML unattended mancante o superiore a 2 MiB.")
        content = path.read_bytes()
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise ValueError(f"XML unattended non leggibile: {exc}") from exc
        if root.tag != "{urn:schemas-microsoft-com:unattend}unattend":
            raise ValueError("Il file non è un answer file Windows unattend valido.")
        return content
    if architecture not in {"amd64", "x86", "arm64"}:
        raise ValueError("Architettura immagine non supportata.")
    ns = "urn:schemas-microsoft-com:unattend"
    ET.register_namespace("", ns)
    wcm = "http://schemas.microsoft.com/WMIConfig/2002/State"
    ET.register_namespace("wcm", wcm)
    def node(parent, tag, text=None, **attrs):
        child = ET.SubElement(parent, f"{{{ns}}}{tag}", attrs)
        if text is not None:
            child.text = str(text)
        return child
    root = ET.Element(f"{{{ns}}}unattend")
    def component(parent, name):
        return node(parent, "component", name=name, processorArchitecture=architecture,
                    publicKeyToken="31bf3856ad364e35", language="neutral", versionScope="nonSxS")
    locale = config.get("locale", "it-IT")
    for pass_name, comp in (("windowsPE", "Microsoft-Windows-International-Core-WinPE"),
                            ("oobeSystem", "Microsoft-Windows-International-Core")):
        settings = node(root, "settings", **{"pass": pass_name})
        intl = component(settings, comp)
        for tag in ("InputLocale", "SystemLocale", "UILanguage", "UserLocale"):
            node(intl, tag, locale)
        if pass_name == "windowsPE":
            ui = node(intl, "SetupUILanguage")
            node(ui, "UILanguage", locale)
            if "disk_id" in config or config.get("accept_eula"):
                setup = component(settings, "Microsoft-Windows-Setup")
                if config.get("accept_eula"):
                    user_data = node(setup, "UserData")
                    node(user_data, "AcceptEula", "true")
                if "disk_id" in config:
                    disk_id = config["disk_id"]
                    disks = node(setup, "DiskConfiguration")
                    disk = node(disks, "Disk", **{f"{{{wcm}}}action": "add"})
                    node(disk, "DiskID", disk_id)
                    node(disk, "WillWipeDisk", "true")
                    creates = node(disk, "CreatePartitions")
                    for order, kind, size in ((1, "EFI", 260), (2, "MSR", 16), (3, "Primary", None)):
                        partition = node(creates, "CreatePartition", **{f"{{{wcm}}}action": "add"})
                        node(partition, "Order", order)
                        node(partition, "Type", kind)
                        node(partition, "Size" if size else "Extend", size if size else "true")
                    modifies = node(disk, "ModifyPartitions")
                    for order, fmt, label in ((1, "FAT32", "System"), (3, "NTFS", "Windows")):
                        partition = node(modifies, "ModifyPartition", **{f"{{{wcm}}}action": "add"})
                        node(partition, "Order", 1 if order == 1 else 2)
                        node(partition, "PartitionID", order)
                        node(partition, "Format", fmt)
                        node(partition, "Label", label)
                        if order == 3:
                            node(partition, "Letter", "C")
                    install = node(setup, "ImageInstall")
                    os_image = node(install, "OSImage")
                    install_from = node(os_image, "InstallFrom")
                    metadata = node(install_from, "MetaData", **{f"{{{wcm}}}action": "add"})
                    node(metadata, "Key", "/IMAGE/INDEX")
                    node(metadata, "Value", 1)
                    target = node(os_image, "InstallTo")
                    node(target, "DiskID", disk_id)
                    node(target, "PartitionID", 3)
    settings = node(root, "settings", **{"pass": "specialize"})
    shell = component(settings, "Microsoft-Windows-Shell-Setup")
    node(shell, "ComputerName", config.get("computer_name", "WINIMAGE"))
    node(shell, "TimeZone", config.get("time_zone", "W. Europe Standard Time"))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def destructive_setup(config):
    if config.get("wipe_disk"):
        return True
    if "xml_path" in config:
        root = ET.fromstring(unattended_xml(config))
        return any(node.tag.endswith("}WillWipeDisk") and (node.text or "").strip().lower() == "true" for node in root.iter())
    return False
