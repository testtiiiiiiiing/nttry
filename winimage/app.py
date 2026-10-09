import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from .backend import ImageTools, is_admin


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WinImage Studio — Gestione immagini Windows")
        self.geometry("1050x720")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.events = queue.Queue()
        self.tools = ImageTools(lambda line: self.events.put(("log", line)))
        self.busy = False
        self.buttons = []
        self.image = tk.StringVar()
        self.index = tk.StringVar(value="1")
        self.directory = tk.StringVar(value=os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "WinImageStudio", "mount"))
        self.status = tk.StringVar(value="Seleziona un’immagine. Le modifiche richiedono privilegi amministratore.")
        ttk.Label(self, text="WinImage Studio", font=("Segoe UI", 22, "bold")).pack(anchor="w", padx=20, pady=(15, 3))
        ttk.Label(self, text="Personalizza copie di immagini Windows offline con gli strumenti Microsoft.").pack(anchor="w", padx=20)
        tabs = ttk.Notebook(self)
        tabs.pack(fill="x", padx=20, pady=15)
        image_tab = ttk.Frame(tabs, padding=12)
        service_tab = ttk.Frame(tabs, padding=12)
        iso_tab = ttk.Frame(tabs, padding=12)
        tabs.add(image_tab, text="Immagine")
        tabs.add(service_tab, text="Driver e componenti")
        tabs.add(iso_tab, text="Supporto ISO")
        self.field(image_tab, "File WIM / ESD", self.image, self.pick_image)
        self.field(image_tab, "Indice dell’edizione", self.index)
        self.field(image_tab, "Cartella di montaggio", self.directory, self.pick_mount)
        row = ttk.Frame(image_tab)
        row.pack(fill="x", pady=10)
        self.button(row, "Mostra edizioni", self.info)
        self.button(row, "Esporta copia WIM…", self.export)
        self.button(row, "Monta WIM", self.mount)
        self.button(row, "Salva e smonta", lambda: self.unmount(True))
        self.button(row, "Scarta e smonta", lambda: self.unmount(False))
        ttk.Label(service_tab, text="Le operazioni agiscono solo sull’immagine montata da questa sessione.").pack(anchor="w")
        row = ttk.Frame(service_tab)
        row.pack(fill="x", pady=10)
        self.button(row, "Aggiungi driver INF…", self.driver)
        self.button(row, "Aggiungi CAB / MSU…", self.package)
        self.button(row, "Elenca driver", lambda: self.execute(lambda: self.tools.service("/Get-Drivers")))
        self.button(row, "Elenca pacchetti", lambda: self.execute(lambda: self.tools.service("/Get-Packages")))
        row = ttk.Frame(service_tab)
        row.pack(fill="x", pady=10)
        self.button(row, "Elenca funzionalità", lambda: self.execute(lambda: self.tools.service("/Get-Features")))
        self.button(row, "Abilita funzionalità…", lambda: self.feature(True))
        self.button(row, "Disabilita funzionalità…", lambda: self.feature(False))
        self.button(row, "Rimuovi pacchetto…", self.remove_package)
        ttk.Label(iso_tab, text="Estrai una ISO, modifica una copia di sources/install.wim, poi ricrea il supporto.\nLa ricostruzione richiede oscdimg.exe del Windows ADK (Deployment Tools).").pack(anchor="w")
        row = ttk.Frame(iso_tab)
        row.pack(fill="x", pady=10)
        self.button(row, "Estrai ISO…", self.extract)
        self.button(row, "Crea ISO BIOS + UEFI…", self.build)
        ttk.Label(self, textvariable=self.status, wraplength=980).pack(anchor="w", padx=20)
        self.log = tk.Text(self, wrap="word", state="disabled", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True, padx=20, pady=12)
        self.after(100, self.poll)

    def field(self, parent, label, variable, browse=None):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=24).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        if browse:
            self.button(row, "Sfoglia…", browse)

    def button(self, parent, label, action):
        button = ttk.Button(parent, text=label, command=action)
        button.pack(side="left", padx=3)
        self.buttons.append(button)

    def execute(self, operation):
        if self.busy:
            return
        if os.name != "nt":
            messagebox.showerror("Windows richiesto", "Le operazioni sulle immagini richiedono Windows.")
            return
        if not is_admin():
            messagebox.showerror("Privilegi richiesti", "Avvia l’applicazione da un terminale eseguito come amministratore.")
            return
        self.busy = True
        self.status.set("Operazione in corso. Attendi il completamento; non chiudere l’applicazione.")
        for button in self.buttons:
            button.state(["disabled"])
        def worker():
            try:
                operation()
                self.events.put(("done", "Operazione completata."))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=False).start()

    def poll(self):
        while True:
            try:
                kind, text = self.events.get_nowait()
            except queue.Empty:
                break
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
            if kind in ("done", "error"):
                self.busy = False
                for button in self.buttons:
                    button.state(["!disabled"])
                mount = self.tools.mount
                self.status.set(f"{text} Immagine montata: {mount or 'nessuna'}")
                if kind == "error":
                    messagebox.showerror("Operazione fallita", text)
        self.after(100, self.poll)

    def pick_image(self):
        value = filedialog.askopenfilename(filetypes=[("Immagini Windows", "*.wim *.esd")])
        if value:
            self.image.set(value)

    def info(self):
        image = self.image.get()
        self.execute(lambda: self.tools.info(image))

    def pick_mount(self):
        value = filedialog.askdirectory()
        if value:
            self.directory.set(value)

    def mount(self):
        image, index, directory = self.image.get(), self.index.get(), self.directory.get()
        if messagebox.askyesno("Monta immagine", "Usa una copia di lavoro: salvare le modifiche aggiornerà questo WIM. Continuare?"):
            self.execute(lambda: self.tools.mount_image(image, index, directory))

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension=".wim", filetypes=[("WIM", "*.wim")])
        image, index = self.image.get(), self.index.get()
        if path:
            self.execute(lambda: self.tools.export(image, index, path))

    def unmount(self, commit):
        prompt = "Salvare le modifiche nel WIM e smontarlo?" if commit else "Scartare tutte le modifiche non salvate e smontare?"
        if messagebox.askyesno("Conferma", prompt):
            self.execute(lambda: self.tools.unmount(commit))

    def driver(self):
        path = filedialog.askdirectory(title="Cartella driver INF")
        if path:
            self.execute(lambda: self.tools.add_driver(path))

    def package(self):
        path = filedialog.askopenfilename(filetypes=[("Aggiornamenti", "*.cab *.msu")])
        if path:
            self.execute(lambda: self.tools.add_package(path))

    def feature(self, enabled):
        name = simpledialog.askstring("Funzionalità", "Nome esatto (vedi Elenca funzionalità):")
        if name and messagebox.askyesno("Conferma", f"{'Abilitare' if enabled else 'Disabilitare'} {name}?"):
            self.execute(lambda: self.tools.feature(name, enabled))

    def remove_package(self):
        name = simpledialog.askstring("Rimuovi pacchetto", "Identità completa (vedi Elenca pacchetti):")
        if name and messagebox.askyesno("Conferma rimozione", "La rimozione può compromettere l’immagine. Rimuovere " + name + "?"):
            self.execute(lambda: self.tools.remove_package(name))

    def extract(self):
        image = filedialog.askopenfilename(filetypes=[("ISO", "*.iso")])
        if not image:
            return
        destination = filedialog.asksaveasfilename(title="Nuova cartella per il contenuto ISO")
        if destination:
            self.execute(lambda: self.tools.extract_iso(image, destination))

    def build(self):
        if self.tools.mount:
            messagebox.showerror("Immagine montata", "Salva e smonta il WIM prima di creare una ISO.")
            return
        source = filedialog.askdirectory(title="Cartella del supporto Windows estratto")
        if not source:
            return
        tool = filedialog.askopenfilename(title="Seleziona oscdimg.exe dal Windows ADK", filetypes=[("Eseguibile", "*.exe")])
        if not tool:
            return
        destination = filedialog.asksaveasfilename(defaultextension=".iso", filetypes=[("ISO", "*.iso")])
        if destination:
            self.execute(lambda: self.tools.build_iso(source, destination, tool))

    def close(self):
        if self.busy or self.tools.mount:
            messagebox.showwarning("Operazione o immagine attiva", "Attendi il completamento e smonta l’immagine prima di chiudere.")
            return
        self.destroy()


def main():
    App().mainloop()
