"""Desktop ISO project editor. Tk widgets are accessed only on the UI thread."""
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from .backend import ImageTools, is_admin
from .plan import Plan, SETTING_LABELS, destructive_setup
from .project import Project

CATEGORIES = {
    'Funzionalità': 'features', 'Pacchetti Windows': 'packages',
    'App provisionate': 'appx', 'Capabilities': 'capabilities', 'Driver installati': 'drivers',
}
LABELS = {'driver': 'Integra driver', 'update': 'Integra aggiornamento',
          'feature_enable': 'Abilita funzionalità', 'feature_disable': 'Disabilita funzionalità',
          'feature_remove': 'Rimuovi payload funzionalità', 'package_remove': 'Rimuovi pacchetto',
          'appx_remove': 'Rimuovi app', 'capability_remove': 'Rimuovi capability',
          'driver_remove': 'Rimuovi driver', 'setting': 'Impostazione', 'service': 'Avvio servizio',
          'post_setup': 'Post-installazione', 'cleanup': 'Pulizia componenti',
          'registry': 'Registro personalizzato', 'scheduled_task': 'Attività pianificata',
          'power_plan': 'Importa piano energetico'}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('WinImage Studio 2 — Personalizza ISO Windows')
        self.geometry('1200x850')
        self.minsize(1000, 700)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.events = queue.Queue()
        self.tools = ImageTools(lambda text: self.events.put(('log', text)))
        self.project = None
        self.plan = Plan()
        self.busy = False
        self.controls = []
        self.iso = tk.StringVar()
        self.root_path = tk.StringVar()
        self.output = tk.StringVar()
        self.oscdimg = tk.StringVar(value=ImageTools.find_oscdimg())
        self.wimlib = tk.StringVar(value=self.tools.wimlib)
        self.edition = tk.StringVar()
        self.category = tk.StringVar(value='Funzionalità')
        self.status = tk.StringVar(value='1. Apri una ISO → 2. Carica edizione → 3. Personalizza → 4. Applica → 5. Crea ISO')
        self.unattended_enabled = tk.BooleanVar()
        self.locale = tk.StringVar(value='it-IT')
        self.computer = tk.StringVar(value='WINIMAGE')
        self.timezone = tk.StringVar(value='W. Europe Standard Time')
        self.disk_id = None
        self.answer_path = None
        self.accept_eula = tk.BooleanVar(value=False)
        self.setup_info = tk.StringVar(value='Nessun partizionamento automatico; OOBE interattivo.')
        ttk.Label(self, text='WinImage Studio', font=('Segoe UI', 23, 'bold')).pack(anchor='w', padx=20, pady=(14, 0))
        ttk.Label(self, text='Editor di ISO Windows • copia di lavoro • preset • coda modifiche').pack(anchor='w', padx=20, pady=(0, 10))
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='both', expand=True, padx=16)
        pages = {}
        for name in ('Sorgente ISO', 'Componenti', 'Integrazione', 'Impostazioni', 'Installazione', 'Applica e ISO'):
            pages[name] = ttk.Frame(self.tabs, padding=12)
            self.tabs.add(pages[name], text=name)
        source = pages['Sorgente ISO']
        self.field(source, 'ISO originale', self.iso, self.pick_iso)
        self.field(source, 'Nuova cartella progetto', self.root_path, self.pick_project)
        self.field(source, 'wimlib-imagex.exe (solo SWM)', self.wimlib, self.pick_wimlib)
        self.row(source, [('Estrai ISO e leggi edizioni', self.create), ('Riapri progetto…', self.reopen)])
        ttk.Label(source, text='Edizione da includere nella nuova ISO (una sola edizione per progetto):').pack(anchor='w', pady=(16, 5))
        self.editions = ttk.Combobox(source, textvariable=self.edition, state='readonly', width=80)
        self.editions.pack(anchor='w')
        self.controls.append(self.editions)
        self.row(source, [('Carica edizione', self.load), ('Scarta modifiche e smonta', self.discard)])
        ttk.Label(source, text='La ISO originale resta intatta. Il progetto conserva supporto estratto, WIM di lavoro, preset e registro.\nServono Windows, amministratore, spazio libero ≥ 25 GiB (o 4× ISO) e Windows ADK per generare la ISO.', wraplength=1060).pack(anchor='w', pady=12)
        components = pages['Componenti']
        self.category_box = ttk.Combobox(components, textvariable=self.category, values=list(CATEGORIES), state='readonly')
        self.category_box.pack(anchor='w')
        self.controls.append(self.category_box)
        self.category_box.bind('<<ComboboxSelected>>', lambda event: self.items.delete(*self.items.get_children()))
        self.row(components, [('Leggi dall’immagine', self.refresh_inventory), ('Abilita selezione', lambda: self.queue_selected('enable')),
                              ('Disabilita selezione', lambda: self.queue_selected('disable')), ('Rimuovi selezione', lambda: self.queue_selected('remove'))])
        self.items = self.tree(components, ('name', 'state'), ('Nome / identità', 'Stato / descrizione'))
        ttk.Label(components, text='Le rimozioni usano API DISM supportate: pacchetti, app provisionate, capabilities, driver OEM e payload delle funzionalità.\nNon eliminano arbitrariamente file di sistema. Una rimozione può rendere l’immagine non installabile.', wraplength=1060).pack(anchor='w', pady=8)
        integration = pages['Integrazione']
        self.row(integration, [('Aggiungi cartella driver INF…', self.add_driver), ('Aggiungi aggiornamenti CAB/MSU…', self.add_updates)])
        self.row(integration, [('Scarica aggiornamenti da manifest…', self.download_updates), ('Esporta driver di questo PC…', self.export_host_drivers)])
        self.row(integration, [('Aggiungi programma/script post-installazione…', self.add_post), ('Pulizia componenti', lambda: self.add('cleanup', 'StartComponentCleanup')),
                              ('Importa piano energetico…', self.add_power)])
        ttk.Label(integration, text='Gli aggiornamenti sono applicati nell’ordine della coda; usa pacchetti Microsoft compatibili.\nGli installer post-setup vengono copiati nell’immagine ed eseguiti durante Windows Setup con privilegi SYSTEM.\nSetupComplete può essere disabilitato da alcune licenze OEM; verifica in VM. Nessun comando post-setup viene eseguito ora.', wraplength=1050).pack(anchor='w', pady=20)
        settings = pages['Impostazioni']
        for key, label in SETTING_LABELS.items():
            self.row(settings, [(label, lambda key=key: self.add('setting', key))])
        self.row(settings, [('Configura servizio…', self.service), ('Valore registro offline…', self.registry), ('Attività pianificata post-setup…', self.task)])
        ttk.Label(settings, text='I criteri possono dipendere dall’edizione Windows. I servizi essenziali di manutenzione sono protetti.\nLe preferenze utente sono applicate al profilo Default, quindi ai nuovi utenti.', wraplength=1050).pack(anchor='w', pady=12)
        install = pages['Installazione']
        toggle = ttk.Checkbutton(install, text='Genera autounattend.xml', variable=self.unattended_enabled)
        toggle.pack(anchor='w', pady=8)
        self.controls.append(toggle)
        eula = ttk.Checkbutton(install, text='Accetta EULA di Windows automaticamente durante Setup (revisionare la licenza)', variable=self.accept_eula)
        eula.pack(anchor='w', pady=4)
        self.controls.append(eula)
        self.field(install, 'Lingua disponibile nella ISO', self.locale)
        self.field(install, 'Nome computer', self.computer)
        self.field(install, 'Fuso orario Windows', self.timezone)
        self.row(install, [('Configura partizionamento UEFI…', self.configure_disk), ('Importa answer file XML…', self.import_answer), ('Ripristina setup interattivo', self.reset_setup)])
        ttk.Label(install, textvariable=self.setup_info, wraplength=1050).pack(anchor='w', pady=8)
        ttk.Label(install, text='Il generatore configura lingua, nome e fuso orario; l’OOBE resta interattivo.\nUn answer file esterno può automatizzare anche OOBE e account. Verifica il file prima di importarlo.\nIl partizionamento UEFI cancella il disco indicato QUANDO LA ISO SARÀ INSTALLATA.', wraplength=1050).pack(anchor='w', pady=15)
        apply = pages['Applica e ISO']
        self.row(apply, [('Salva preset…', self.save_preset), ('Carica preset…', self.load_preset), ('Rimuovi dalla coda', self.remove_queued),
                        ('Sposta su', lambda: self.move(-1)), ('Sposta giù', lambda: self.move(1))])
        self.operations = self.tree(apply, ('kind', 'value'), ('Operazione', 'Valore / percorso'))
        self.field(apply, 'oscdimg.exe (Windows ADK)', self.oscdimg, self.pick_tool)
        self.field(apply, 'Nuova ISO di destinazione', self.output, self.pick_output)
        self.row(apply, [('Applica piano e salva WIM', self.apply), ('Crea ISO avviabile', self.build)])
        ttk.Label(self, textvariable=self.status, wraplength=1160).pack(anchor='w', padx=18, pady=8)
        frame = ttk.Frame(self)
        frame.pack(fill='x', padx=16, pady=(0, 12))
        self.log = tk.Text(frame, height=9, font=('Consolas', 9), wrap='word', state='disabled')
        self.log.pack(fill='x')
        self.after(100, self.poll)

    def row(self, parent, actions):
        frame = ttk.Frame(parent)
        frame.pack(fill='x', pady=5)
        for label, action in actions:
            widget = ttk.Button(frame, text=label, command=action)
            widget.pack(side='left', padx=(0, 5))
            self.controls.append(widget)

    def field(self, parent, label, variable, browse=None):
        frame = ttk.Frame(parent)
        frame.pack(fill='x', pady=5)
        ttk.Label(frame, text=label, width=28).pack(side='left')
        entry = ttk.Entry(frame, textvariable=variable)
        entry.pack(side='left', fill='x', expand=True)
        self.controls.append(entry)
        if browse:
            button = ttk.Button(frame, text='Sfoglia…', command=browse)
            button.pack(side='left', padx=5)
            self.controls.append(button)

    def tree(self, parent, columns, labels):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True, pady=8)
        tree = ttk.Treeview(frame, columns=columns, show='headings', height=8, selectmode='extended')
        for column, label in zip(columns, labels):
            tree.heading(column, text=label)
            tree.column(column, width=650 if column in ('name', 'value') else 200)
        scroll = ttk.Scrollbar(frame, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        return tree

    def execute(self, operation):
        if self.busy:
            return
        if not is_admin():
            messagebox.showerror('Windows amministratore richiesto', 'Avvia su Windows da un terminale amministratore o usa l’eseguibile con richiesta UAC.')
            return
        self.busy = True
        self.status.set('Operazione in corso… consulta il registro. Non interrompere il processo.')
        for widget in self.controls:
            widget.state(['disabled'])
        def worker():
            try:
                result = operation()
                self.events.put(('done', result))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=False).start()

    def poll(self):
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == 'log':
                self.log.configure(state='normal')
                self.log.insert('end', str(value) + '\n')
                self.log.see('end')
                self.log.configure(state='disabled')
            elif kind in ('done', 'error'):
                self.busy = False
                for widget in self.controls:
                    widget.state(['!disabled'])
                stage = self.project.state.get('stage', 'nessuno') if self.project else 'nessuno'
                self.status.set(f"{'Operazione completata' if kind == 'done' else value} • Stato progetto: {stage}")
                if kind == 'error':
                    messagebox.showerror('Operazione fallita', value)
                elif isinstance(value, dict) and 'inventory' in value:
                    self.items.delete(*self.items.get_children())
                    for item in value['inventory']:
                        self.items.insert('', 'end', values=(item['name'], item['state']))
                elif isinstance(value, dict) and 'preset_path' in value:
                    try:
                        self.set_plan(Plan.load(value['preset_path']))
                    except Exception as exc:
                        messagebox.showerror('Preset progetto', str(exc))
                elif isinstance(value, dict) and 'updates' in value:
                    for path in value['updates']:
                        self.add('update', path)
                elif isinstance(value, dict) and 'driver_path' in value:
                    self.add('driver', value['driver_path'])
                if self.project:
                    self.editions['values'] = [f"{e['index']} — {e.get('name', 'Windows')}" for e in self.project.state.get('editions', [])]
                    if not self.edition.get() and self.editions['values']:
                        self.edition.set(self.editions['values'][0])
        self.after(100, self.poll)

    def editable(self):
        if self.busy or (self.project and self.project.state.get('plan_hash')):
            messagebox.showwarning('Piano bloccato', 'Un’operazione è in corso o il piano è già iniziato. Scarta il montaggio per ricominciare.')
            return False
        return True

    def add(self, kind, value, **extra):
        if not self.editable():
            return
        operation = dict(kind=kind, value=value, **extra)
        try:
            Plan(self.plan.operations + [operation]).validate()
        except ValueError as exc:
            messagebox.showerror('Valore non valido', str(exc))
            return
        if operation not in self.plan.operations:
            self.plan.operations.append(operation)
        self.render_plan()

    def render_plan(self):
        self.operations.delete(*self.operations.get_children())
        for i, op in enumerate(self.plan.operations):
            value = SETTING_LABELS.get(op['value'], op['value'])
            if op['kind'] == 'service':
                value += f" → Start={op['start']}"
            self.operations.insert('', 'end', iid=str(i), values=(LABELS[op['kind']], value))

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

    def refresh_inventory(self):
        if not self.project:
            return
        category = CATEGORIES[self.category.get()]
        self.execute(lambda: {'inventory': self.project.list_items(category)})

    def queue_selected(self, action):
        category = CATEGORIES[self.category.get()]
        kind = ('feature_' + action) if category == 'features' else {'packages': 'package_remove', 'appx': 'appx_remove', 'capabilities': 'capability_remove', 'drivers': 'driver_remove'}[category]
        if category != 'features' and action != 'remove':
            messagebox.showinfo('Operazione disponibile', 'Per questa categoria è disponibile solo la rimozione.')
            return
        selected = [self.items.item(i, 'values')[0] for i in self.items.selection()]
        if selected and action == 'remove' and not messagebox.askyesno('Rimozione componenti', f'Accodare {len(selected)} rimozioni? Per le funzionalità verrà rimosso anche il payload.'):
            return
        for name in selected:
            self.add(kind, name)

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

    def remove_queued(self):
        if self.editable():
            for index in sorted((int(i) for i in self.operations.selection()), reverse=True):
                self.plan.operations.pop(index)
            self.render_plan()

    def move(self, delta):
        selected = self.operations.selection()
        if len(selected) == 1 and self.editable():
            i = int(selected[0]); j = i + delta
            if 0 <= j < len(self.plan.operations):
                self.plan.operations[i], self.plan.operations[j] = self.plan.operations[j], self.plan.operations[i]
                self.render_plan()
                self.operations.selection_set(str(j))

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

    def discard(self):
        if self.project and messagebox.askyesno('Scarta', 'Scartare le modifiche al WIM di lavoro e smontarlo?'):
            self.execute(self.project.discard)

    def close(self):
        if self.busy or self.tools.mount:
            messagebox.showwarning('Immagine attiva', 'Attendi e salva o scarta il montaggio prima di chiudere.')
            return
        self.destroy()


def main():
    App().mainloop()
