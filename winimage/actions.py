"""ISO workflow dialogs, separated from the desktop presentation."""
import os
from tkinter import filedialog, messagebox, simpledialog
from .plan import Plan, destructive_setup
from .project import Project


class WorkflowActions:
    def pick_iso(self):
        path = filedialog.askopenfilename(filetypes=[('ISO Windows', '*.iso')])
        if path:
            self.iso.set(path)

    def pick_project(self):
        parent = filedialog.askdirectory(title='Cartella padre del nuovo progetto')
        if parent:
            name = simpledialog.askstring('Progetto', 'Nome della nuova cartella:', initialvalue='WinImageProject')
            if name and os.path.basename(name) == name and name not in ('.', '..'):
                self.root_path.set(os.path.join(parent, name))

    def pick_output(self):
        path = filedialog.asksaveasfilename(defaultextension='.iso', filetypes=[('ISO', '*.iso')])
        if path:
            self.output.set(path)

    def pick_tool(self):
        path = filedialog.askopenfilename(title='oscdimg.exe del Windows ADK', filetypes=[('Eseguibile', '*.exe')])
        if path:
            self.oscdimg.set(path)

    def pick_wimlib(self):
        path = filedialog.askopenfilename(title='wimlib-imagex.exe', filetypes=[('Eseguibile', '*.exe')])
        if path:
            self.wimlib.set(path)

    def create(self):
        if self.project:
            messagebox.showwarning('Progetto aperto', 'Chiudi e riavvia il programma prima di aprire un altro progetto.')
            return
        iso, root = self.iso.get(), self.root_path.get()
        self.tools.wimlib = self.wimlib.get()
        if not iso or not root:
            messagebox.showerror('Percorsi mancanti', 'Seleziona ISO e nuova cartella progetto.')
            return
        def operation():
            project = Project(root, self.tools)
            project.create(iso)
            self.project = project
        self.execute(operation)

    def reopen(self):
        if self.project:
            return
        root = filedialog.askdirectory(title='Progetto contenente project.json')
        if root:
            def operation():
                self.project = Project.open(root, self.tools)
                preset = self.project.root / 'applied-preset.json'
                if preset.exists():
                    return {'preset_path': str(preset)}
            self.execute(operation)

    def load(self):
        if not self.project:
            return
        self.tools.wimlib = self.wimlib.get()
        try:
            index = int(self.edition.get().split(' — ')[0])
        except ValueError:
            messagebox.showerror('Edizione', 'Seleziona un’edizione.')
            return
        self.execute(lambda: self.project.load_edition(index))

    def add_driver(self):
        path = filedialog.askdirectory(title='Cartella contenente driver INF')
        if path:
            self.add('driver', path)

    def add_updates(self):
        for path in filedialog.askopenfilenames(filetypes=[('Aggiornamenti', '*.cab *.msu')]):
            self.add('update', path)

    def download_updates(self):
        if not self.editable():
            return
        manifest = filedialog.askopenfilename(title='Manifest con URL Microsoft e SHA-256', filetypes=[('Manifest aggiornamenti', '*.json')])
        if manifest:
            cache = filedialog.askdirectory(title='Cache persistente dei download')
            if cache:
                from .updates import download_updates
                self.execute(lambda: {'updates': download_updates(manifest, cache, self.tools.emit)})

    def export_host_drivers(self):
        if not self.editable():
            return
        parent = filedialog.askdirectory(title='Cartella padre per l’esportazione driver del PC Windows attuale')
        if parent:
            name = simpledialog.askstring('Cartella driver', 'Nome nuova cartella:', initialvalue='HostDrivers')
            if name and os.path.basename(name) == name and name not in ('.', '..'):
                destination = os.path.join(parent, name)
                self.execute(lambda: {'driver_path': self.tools.export_host_drivers(destination)})

    def add_post(self):
        path = filedialog.askopenfilename(filetypes=[('Installer e script', '*.exe *.msi *.cmd *.bat')])
        if path:
            args = simpledialog.askstring('Opzioni installer', 'Opzioni silenziose del produttore (MSI: /qn già incluso):', initialvalue='')
            if args is not None:
                self.add('post_setup', path, args=args)

    def add_power(self):
        path = filedialog.askopenfilename(filetypes=[('Piano energetico Windows', '*.pow')])
        if path:
            self.add('power_plan', path)

    def service(self):
        name = simpledialog.askstring('Servizio', 'Nome interno del servizio, non il nome visualizzato:')
        if name:
            mode = simpledialog.askinteger('Avvio', '2 = automatico, 3 = manuale, 4 = disabilitato', minvalue=2, maxvalue=4)
            if mode is not None:
                self.add('service', name, start=mode)

    def registry(self):
        hive = simpledialog.askstring('Hive offline', 'SOFTWARE, SYSTEM o DEFAULTUSER:', initialvalue='SOFTWARE')
        if not hive:
            return
        key = simpledialog.askstring('Chiave', 'Chiave relativa all’hive (SYSTEM: @CURRENT@\\... per il ControlSet):')
        if not key:
            return
        name = simpledialog.askstring('Valore', 'Nome del valore:')
        if not name:
            return
        value_type = simpledialog.askstring('Tipo', 'REG_DWORD oppure REG_SZ:', initialvalue='REG_DWORD')
        if not value_type:
            return
        data = simpledialog.askstring('Dati', 'Dati da scrivere:')
        if data is not None:
            self.add('registry', key, hive=hive.upper(), name=name, type=value_type.upper(), data=data)

    def task(self):
        name = simpledialog.askstring('Attività', 'Percorso completo dell’attività pianificata (es. \\Microsoft\\Windows\\...):')
        if name:
            mode = simpledialog.askstring('Azione', 'enable, disable oppure delete:', initialvalue='disable')
            if mode:
                self.add('scheduled_task', name, action=mode)

    def current_plan(self):
        self.plan.unattended = {'locale': self.locale.get(), 'computer_name': self.computer.get(), 'time_zone': self.timezone.get()} if self.unattended_enabled.get() else {}
        if self.plan.unattended and self.disk_id is not None:
            self.plan.unattended.update(disk_id=self.disk_id, wipe_disk=True)
        if self.plan.unattended:
            self.plan.unattended['accept_eula'] = self.accept_eula.get()
        if self.plan.unattended and self.answer_path:
            self.plan.unattended = {'xml_path': self.answer_path}
        return self.plan.validate()

    def configure_disk(self):
        if not self.editable():
            return
        disk = simpledialog.askinteger('Disco destinazione durante Setup', 'Numero disco da CANCELLARE durante l’installazione in modalità UEFI:', minvalue=0, maxvalue=31)
        if disk is not None:
            phrase = simpledialog.askstring('Conferma cancellazione futura', f'Digita CANCELLA DISCO {disk} per generare il partizionamento:')
            if phrase == f'CANCELLA DISCO {disk}':
                self.disk_id = disk
                self.answer_path = None
                self.unattended_enabled.set(True)
                self.setup_info.set(f'ATTENZIONE: la ISO cancellerà il disco {disk} durante Setup UEFI (EFI + MSR + Windows).')

    def import_answer(self):
        if not self.editable():
            return
        path = filedialog.askopenfilename(filetypes=[('Windows answer file', '*.xml')])
        if path:
            try:
                from .plan import unattended_xml
                unattended_xml({'xml_path': path})
                self.answer_path = path
                self.disk_id = None
                self.unattended_enabled.set(True)
                self.setup_info.set(f'Answer file esterno: {path}. Può contenere comandi, credenziali e partizionamento.')
            except Exception as exc:
                messagebox.showerror('XML non valido', str(exc))

    def reset_setup(self):
        if self.editable():
            self.disk_id = None
            self.answer_path = None
            self.setup_info.set('Nessun partizionamento automatico; OOBE interattivo.')

    def save_preset(self):
        path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('Preset', '*.json')])
        if path:
            try:
                self.current_plan().save(path)
            except Exception as exc:
                messagebox.showerror('Preset', str(exc))

    def load_preset(self):
        if not self.editable():
            return
        path = filedialog.askopenfilename(filetypes=[('Preset', '*.json')])
        if path:
            try:
                self.set_plan(Plan.load(path))
            except Exception as exc:
                messagebox.showerror('Preset', str(exc))

    def set_plan(self, plan):
        self.plan = plan
        self.unattended_enabled.set(bool(plan.unattended))
        self.disk_id = plan.unattended.get('disk_id')
        self.answer_path = plan.unattended.get('xml_path')
        self.accept_eula.set(plan.unattended.get('accept_eula', False))
        self.setup_info.set(f'Setup da preset: disco {self.disk_id}, XML {self.answer_path or "generato"}. Revisionare prima di applicare.')
        for key, variable in [('locale', self.locale), ('computer_name', self.computer), ('time_zone', self.timezone)]:
            variable.set(plan.unattended.get(key, {'locale': 'it-IT', 'computer_name': 'WINIMAGE', 'time_zone': 'W. Europe Standard Time'}[key]))
        self.render_plan()

    def apply(self):
        if not self.project:
            return
        try:
            plan = self.current_plan()
            erases_disk = destructive_setup(plan.unattended)
        except ValueError as exc:
            messagebox.showerror('Piano', str(exc))
            return
        if erases_disk and not messagebox.askyesno('ISO con cancellazione dischi', 'Questo answer file cancellerà un disco durante Windows Setup. Hai verificato disco, backup e destinazione?'):
            return
        if messagebox.askyesno('Applica alla copia WIM', f'Applicare {len(plan.operations)} operazioni e salvare? Verifica la coda e l’ordine degli aggiornamenti prima di continuare.'):
            self.execute(lambda: self.project.apply(plan))

    def build(self):
        if self.project:
            destination, tool = self.output.get(), self.oscdimg.get()
            if not destination or not tool:
                messagebox.showerror('Percorsi mancanti', 'Seleziona oscdimg.exe e una nuova ISO di destinazione.')
                return
            self.execute(lambda: self.project.build(destination, tool))

    def close(self):
        if self.busy or self.tools.mount:
            messagebox.showwarning('Immagine attiva', 'Attendi e salva o scarta il montaggio prima di chiudere.')
            return
        self.destroy()
