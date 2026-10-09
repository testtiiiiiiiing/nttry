"""WinImage Studio 3: ISO workspace and interactive component catalogue."""
from collections import defaultdict
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from .actions import WorkflowActions
from .backend import ImageTools, is_admin
from .components import Catalogue, CATEGORY_LABELS, OP_CATEGORY, natural
from .plan import Plan, SETTING_LABELS

CATEGORIES = {label: key for key, label in CATEGORY_LABELS.items()}
LABELS = {'driver': 'Integra driver', 'update': 'Integra aggiornamento',
          'feature_enable': 'Abilita funzionalita', 'feature_disable': 'Disabilita funzionalita',
          'feature_remove': 'Rimuovi funzionalita', 'package_remove': 'Rimuovi pacchetto',
          'appx_remove': 'Rimuovi app', 'capability_remove': 'Rimuovi capability',
          'driver_remove': 'Rimuovi driver', 'setting': 'Impostazione', 'service': 'Avvio servizio',
          'post_setup': 'Post-installazione', 'cleanup': 'Pulizia componenti',
          'registry': 'Registro personalizzato', 'scheduled_task': 'Attivita pianificata', 'power_plan': 'Piano energetico'}
PAGES = [('ISO e progetto', 'Prepara una copia della ISO e scegli l’edizione Windows.'),
         ('Componenti', 'Ordina per tipo, scegli cosa mantenere e vedi subito le modifiche.'),
         ('Integrazione', 'Aggiungi driver, aggiornamenti e programmi al supporto.'),
         ('Impostazioni', 'Configura Windows prima della sua installazione.'),
         ('Installazione', 'Prepara lingua, nome computer e installazione automatizzata.'),
         ('Modifiche e ISO', 'Revisiona il piano, salva l’immagine e genera la nuova ISO.')]


class App(WorkflowActions, tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('WinImage Studio 3 - Personalizzazione ISO Windows')
        self.geometry('1360x900')
        self.minsize(1150, 740)
        self.configure(background='#f4f6fa')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.events = queue.Queue()
        self.tools = ImageTools(lambda text: self.events.put(('log', text)))
        self.project = None
        self.plan = Plan()
        self.catalogue = Catalogue()
        self.busy = False
        self.controls = []
        self.row_keys = {}
        self.group_nodes, self.group_expansion = {}, {}
        self.sort_column, self.sort_reverse = 'type', False
        self.iso, self.root_path, self.output = (tk.StringVar() for _ in range(3))
        self.oscdimg = tk.StringVar(value=ImageTools.find_oscdimg())
        self.wimlib = tk.StringVar(value=self.tools.wimlib)
        self.edition = tk.StringVar()
        self.category = tk.StringVar(value='Tutti i tipi')
        self.search = tk.StringVar()
        self.grouped = tk.BooleanVar(value=True)
        self.show_removed = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='Apri una ISO Windows per iniziare.')
        self.summary = tk.StringVar()
        self.pending_count = tk.StringVar(value='Nessuna modifica in attesa')
        self.selection_info = tk.StringVar(value='Seleziona uno o piu componenti per modificarli.')
        self.unattended_enabled = tk.BooleanVar()
        self.locale = tk.StringVar(value='it-IT')
        self.computer = tk.StringVar(value='WINIMAGE')
        self.timezone = tk.StringVar(value='W. Europe Standard Time')
        self.disk_id = self.answer_path = None
        self.accept_eula = tk.BooleanVar(value=False)
        self.setup_info = tk.StringVar(value='Nessun partizionamento automatico; OOBE interattivo.')
        self.page_title, self.page_subtitle = tk.StringVar(), tk.StringVar()
        self._style()
        self._layout()
        self.search.trace_add('write', lambda *args: self.render_components())
        self.render_plan()
        self.select_page('ISO e progetto')
        self.poll_id = self.after(100, self.poll)

    def _style(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background='#f4f6fa', foreground='#202c40')
        style.configure('TFrame', background='#f4f6fa')
        style.configure('TLabel', background='#f4f6fa')
        style.configure('Title.TLabel', font=('Segoe UI', 22, 'bold'), foreground='#152b4a')
        style.configure('Subtitle.TLabel', foreground='#65748b')
        style.configure('TButton', padding=(12, 8), background='#ffffff', bordercolor='#d3dcea', lightcolor='#ffffff', darkcolor='#d3dcea')
        style.map('TButton', background=[('active', '#e8effa'), ('disabled', '#eef1f6')], foreground=[('disabled', '#9aa6b6')])
        style.configure('Primary.TButton', background='#2162df', foreground='white', bordercolor='#2162df')
        style.map('Primary.TButton', background=[('active', '#164dc0'), ('disabled', '#b0c3e9')], foreground=[('disabled', '#ffffff')])
        style.configure('Danger.TButton', foreground='#b33040')
        style.configure('Treeview', rowheight=31, background='#ffffff', fieldbackground='#ffffff', bordercolor='#dbe2ec', font=('Segoe UI', 10))
        style.configure('Treeview.Heading', background='#eaf0f8', font=('Segoe UI', 10, 'bold'), padding=(8, 9))
        style.map('Treeview', background=[('selected', '#2162df')], foreground=[('selected', '#ffffff')])
        style.configure('TEntry', padding=7, fieldbackground='#ffffff')
        style.configure('TCombobox', padding=6, fieldbackground='#ffffff')
        style.configure('Section.TLabel', font=('Segoe UI', 13, 'bold'), foreground='#183659')

    def _layout(self):
        sidebar = tk.Frame(self, background='#14243a', width=218)
        sidebar.pack(side='left', fill='y')
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text='WINIMAGE', background='#14243a', foreground='white', font=('Segoe UI', 18, 'bold')).pack(anchor='w', padx=22, pady=(26, 3))
        tk.Label(sidebar, text='STUDIO  /  03', background='#14243a', foreground='#9eb2d2', font=('Segoe UI', 10)).pack(anchor='w', padx=23, pady=(0, 32))
        self.nav_buttons = {}
        for i, (title, subtitle) in enumerate(PAGES, 1):
            button = tk.Button(sidebar, text=f'{i:02d}   {title}', anchor='w', font=('Segoe UI', 11), background='#14243a', foreground='#b9c8dd',
                               activebackground='#244266', activeforeground='white', relief='flat', borderwidth=0, padx=18, pady=13,
                               command=lambda title=title: self.select_page(title))
            button.pack(fill='x', padx=10, pady=3)
            self.nav_buttons[title] = button
        tk.Label(sidebar, textvariable=self.pending_count, wraplength=175, justify='left', background='#14243a', foreground='#8fafdf', font=('Segoe UI', 10)).pack(side='bottom', anchor='w', padx=22, pady=26)
        content = ttk.Frame(self, padding=(24, 20))
        content.pack(side='left', fill='both', expand=True)
        header = ttk.Frame(content)
        header.pack(fill='x', pady=(0, 18))
        ttk.Label(header, textvariable=self.page_title, style='Title.TLabel').pack(anchor='w')
        ttk.Label(header, textvariable=self.page_subtitle, style='Subtitle.TLabel').pack(anchor='w', pady=(4, 0))
        footer = ttk.Frame(content)
        footer.pack(side='bottom', fill='x', pady=(12, 0))
        status_row = ttk.Frame(footer)
        status_row.pack(fill='x')
        ttk.Label(status_row, textvariable=self.status, wraplength=840).pack(side='left', fill='x', expand=True)
        ttk.Button(status_row, text='Registro', command=self.toggle_log).pack(side='right')
        self.log = tk.Text(footer, height=7, background='#182539', foreground='#d7e3f8', font=('Consolas', 9), relief='flat', wrap='word', state='disabled')
        self.progress = ttk.Progressbar(footer, mode='indeterminate')
        self.page_host = ttk.Frame(content)
        self.page_host.pack(fill='both', expand=True)
        self.page_host.rowconfigure(0, weight=1)
        self.page_host.columnconfigure(0, weight=1)
        self.pages = {}
        for title, subtitle in PAGES:
            page = ttk.Frame(self.page_host)
            page.grid(row=0, column=0, sticky='nsew')
            self.pages[title] = page
        self._source_page(self.pages['ISO e progetto'])
        self._component_page(self.pages['Componenti'])
        self._integration_page(self.pages['Integrazione'])
        self._settings_page(self.pages['Impostazioni'])
        self._install_page(self.pages['Installazione'])
        self._apply_page(self.pages['Modifiche e ISO'])

    def select_page(self, title):
        self.pages[title].tkraise()
        self.page_title.set(title)
        self.page_subtitle.set(dict(PAGES)[title])
        for name, button in self.nav_buttons.items():
            button.configure(background='#254979' if name == title else '#14243a', foreground='white' if name == title else '#b9c8dd')

    def section(self, parent, title, text=None):
        ttk.Label(parent, text=title, style='Section.TLabel').pack(anchor='w', pady=(16, 9))
        if text:
            ttk.Label(parent, text=text, style='Subtitle.TLabel', wraplength=880).pack(anchor='w', pady=(0, 10))

    def row(self, parent, actions):
        frame = ttk.Frame(parent)
        frame.pack(fill='x', pady=6)
        buttons = []
        for entry in actions:
            label, command = entry[:2]
            style = entry[2] if len(entry) > 2 else 'TButton'
            button = ttk.Button(frame, text=label, command=command, style=style)
            button.pack(side='left', padx=(0, 7))
            self.controls.append(button)
            buttons.append(button)
        return buttons

    def field(self, parent, label, variable, browse=None):
        frame = ttk.Frame(parent)
        frame.pack(fill='x', pady=6)
        ttk.Label(frame, text=label, width=28).pack(side='left')
        entry = ttk.Entry(frame, textvariable=variable)
        entry.pack(side='left', fill='x', expand=True)
        self.controls.append(entry)
        if browse:
            self.row_button(frame, 'Sfoglia...', browse)

    def row_button(self, parent, text, command):
        button = ttk.Button(parent, text=text, command=command)
        button.pack(side='left', padx=(7, 0))
        self.controls.append(button)
        return button

    def tree(self, parent, columns, labels, grouped=False):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True, pady=10)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        tree = ttk.Treeview(frame, columns=columns, show='tree headings' if grouped else 'headings', selectmode='extended')
        tree.column('#0', width=25, minwidth=25, stretch=False)
        for column, label in zip(columns, labels):
            tree.heading(column, text=label)
            tree.column(column, width=170, minwidth=100)
        vertical = ttk.Scrollbar(frame, command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        return tree

    def _source_page(self, page):
        self.section(page, '1. Apri il supporto Windows', 'La ISO originale viene conservata. Tutte le modifiche avvengono nella copia del progetto.')
        self.field(page, 'ISO originale', self.iso, self.pick_iso)
        self.field(page, 'Nuova cartella progetto', self.root_path, self.pick_project)
        self.field(page, 'wimlib (solo immagini SWM)', self.wimlib, self.pick_wimlib)
        self.row(page, [('Estrai ISO', self.create, 'Primary.TButton'), ('Riapri progetto', self.reopen)])
        self.section(page, '2. Scegli l’edizione', 'Il supporto personalizzato conterra una sola edizione Windows.')
        self.editions = ttk.Combobox(page, textvariable=self.edition, state='readonly')
        self.editions.pack(fill='x', pady=6)
        self.controls.append(self.editions)
        self.row(page, [('Carica edizione', self.load, 'Primary.TButton'), ('Scarta e smonta', self.discard)])
        self.section(page, 'Requisiti', 'Windows, privilegi amministratore, DISM compatibile e almeno 25 GiB liberi (o 4 volte la ISO). Windows ADK serve per creare la ISO finale.')

    def _component_page(self, page):
        filters = ttk.Frame(page)
        filters.pack(fill='x')
        ttk.Label(filters, text='Tipo').pack(side='left', padx=(0, 8))
        self.category_box = ttk.Combobox(filters, textvariable=self.category, values=['Tutti i tipi', *CATEGORIES], state='readonly', width=22)
        self.category_box.pack(side='left')
        self.category_box.bind('<<ComboboxSelected>>', lambda event: self.render_components())
        self.controls.append(self.category_box)
        ttk.Label(filters, text='Cerca').pack(side='left', padx=(18, 8))
        search = ttk.Entry(filters, textvariable=self.search)
        search.pack(side='left', fill='x', expand=True)
        self.controls.append(search)
        self.row_button(filters, 'Aggiorna elenco', self.refresh_inventory)
        self.action_buttons = dict(zip(('enable', 'disable', 'remove', 'undo'), self.row(page, [
            ('Abilita', lambda: self.queue_selected('enable')),
            ('Disabilita', lambda: self.queue_selected('disable')),
            ('Rimuovi', lambda: self.queue_selected('remove'), 'Danger.TButton'),
            ('Annulla modifica', lambda: self.queue_selected('undo'))])))
        options = ttk.Frame(page)
        options.pack(fill='x', pady=3)
        for text, variable in [('Raggruppa per tipo', self.grouped), ('Mostra rimozioni in attesa', self.show_removed)]:
            check = ttk.Checkbutton(options, text=text, variable=variable, command=self.render_components)
            check.pack(side='left', padx=(0, 18))
            self.controls.append(check)
        ttk.Label(options, textvariable=self.summary, style='Subtitle.TLabel').pack(side='right')
        self.items = self.tree(page, ('type', 'name', 'projected', 'actual', 'pending'),
                               ('Tipo', 'Componente', 'Stato previsto', 'Stato immagine', 'Modifica'), grouped=True)
        self.items.column('type', width=205)
        self.items.column('name', width=300)
        self.items.column('projected', width=145)
        self.items.column('actual', width=145)
        self.items.column('pending', width=170)
        for column in self.items['columns']:
            self.items.heading(column, command=lambda column=column: self.sort_components(column))
        self.items.tag_configure('pending', foreground='#935a00', background='#fff7e5')
        self.items.tag_configure('removed', foreground='#ac3649', background='#fff0f2')
        self.items.tag_configure('group', background='#e9eff8', foreground='#173761', font=('Segoe UI', 10, 'bold'))
        self.items.bind('<<TreeviewSelect>>', self.selection_changed)
        self.items.bind('<Delete>', lambda event: self.queue_selected('remove'))
        ttk.Label(page, textvariable=self.selection_info, style='Subtitle.TLabel').pack(anchor='w')
        self.details = tk.Text(page, height=3, wrap='word', relief='flat', background='#eaf0f7', foreground='#38516e', font=('Segoe UI', 9), state='disabled')
        self.details.pack(fill='x', pady=(6, 8))
        ttk.Label(page, text='Le scelte aggiornano subito questa vista. La copia WIM viene modificata quando premi Applica nella pagina Modifiche e ISO.', wraplength=950, style='Subtitle.TLabel').pack(anchor='w')

    def _integration_page(self, page):
        self.section(page, 'Driver e aggiornamenti')
        self.row(page, [('Cartella driver INF', self.add_driver), ('Aggiornamenti CAB / MSU', self.add_updates)])
        self.row(page, [('Download da manifest', self.download_updates), ('Esporta driver del PC', self.export_host_drivers)])
        self.section(page, 'Dopo l’installazione', 'Gli installer e gli script vengono inclusi nel supporto e avviati da SetupComplete. Usa le opzioni silenziose del produttore.')
        self.row(page, [('Programma o script', self.add_post), ('Piano energetico', self.add_power)])
        self.section(page, 'Ottimizzazione')
        self.row(page, [('Accoda pulizia componenti', lambda: self.add('cleanup', 'StartComponentCleanup'))])
        ttk.Label(page, text='Gli aggiornamenti seguono l’ordine della coda. I download verificano SHA-256 e usano una cache persistente.', wraplength=930, style='Subtitle.TLabel').pack(anchor='w', pady=16)

    def _settings_page(self, page):
        self.section(page, 'Preferenze e criteri Windows')
        for key, label in SETTING_LABELS.items():
            self.row(page, [(label, lambda key=key: self.add('setting', key))])
        self.section(page, 'Configurazione avanzata')
        self.row(page, [('Servizio', self.service), ('Registro offline', self.registry), ('Attivita pianificata', self.task)])
        ttk.Label(page, text='Le preferenze del profilo Default valgono per i nuovi utenti. L’effetto dei criteri puo dipendere dall’edizione Windows.', style='Subtitle.TLabel', wraplength=920).pack(anchor='w', pady=16)

    def _install_page(self, page):
        self.section(page, 'Installazione automatizzata')
        for text, variable in [('Genera autounattend.xml', self.unattended_enabled), ('Accetta EULA durante Setup (revisionare la licenza)', self.accept_eula)]:
            check = ttk.Checkbutton(page, text=text, variable=variable)
            check.pack(anchor='w', pady=7)
            self.controls.append(check)
        self.field(page, 'Lingua disponibile nella ISO', self.locale)
        self.field(page, 'Nome computer', self.computer)
        self.field(page, 'Fuso orario Windows', self.timezone)
        self.section(page, 'Disco e answer file')
        self.row(page, [('Partizionamento UEFI', self.configure_disk), ('Importa XML', self.import_answer), ('Setup interattivo', self.reset_setup)])
        ttk.Label(page, textvariable=self.setup_info, wraplength=920).pack(anchor='w', pady=10)
        ttk.Label(page, text='Il partizionamento automatico cancella il disco indicato DURANTE l’installazione della ISO. Il generatore lascia OOBE e account interattivi; usa un answer file esterno per completarli.', wraplength=920, style='Subtitle.TLabel').pack(anchor='w', pady=14)

    def _apply_page(self, page):
        self.row(page, [('Salva preset', self.save_preset), ('Carica preset', self.load_preset),
                        ('Annulla selezione', self.remove_queued), ('Sposta su', lambda: self.move(-1)), ('Sposta giu', lambda: self.move(1))])
        self.operations = self.tree(page, ('kind', 'value', 'state'), ('Operazione', 'Componente / valore', 'Stato'))
        self.operations.column('value', width=500)
        self.field(page, 'oscdimg.exe (Windows ADK)', self.oscdimg, self.pick_tool)
        self.field(page, 'Nuova ISO di destinazione', self.output, self.pick_output)
        self.row(page, [('Applica e salva immagine', self.apply, 'Primary.TButton'), ('Crea ISO avviabile', self.build, 'Primary.TButton')])

    def toggle_log(self):
        if self.log.winfo_manager():
            self.log.pack_forget()
        else:
            self.log.pack(fill='x', pady=(10, 0))

    def execute(self, operation):
        if self.busy:
            return
        if not is_admin():
            messagebox.showerror('Windows amministratore richiesto', 'Avvia il programma su Windows con privilegi amministratore.')
            return
        self.busy = True
        self.status.set('Operazione in corso. Non interrompere il processo.')
        self.progress.pack(fill='x', pady=(8, 0))
        self.progress.start(15)
        for widget in self.controls:
            widget.state(['disabled'])
        def worker():
            try:
                self.events.put(('done', operation()))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=False).start()

    def completed(self):
        return self.project.state.get('completed', 0) if self.project else 0

    def poll(self):
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == 'log':
                self.log.configure(state='normal')
                self.log.insert('end', str(value) + '\n')
                self.log.see('end')
                self.log.configure(state='disabled')
                continue
            if kind not in ('done', 'error'):
                continue
            self.busy = False
            self.progress.stop()
            self.progress.pack_forget()
            for widget in self.controls:
                widget.state(['!disabled'])
            stage = self.project.state.get('stage', 'nessuno') if self.project else 'nessuno'
            self.status.set(f"{'Operazione completata' if kind == 'done' else value} | Progetto: {stage}")
            if isinstance(value, dict) and kind == 'done':
                if 'catalogue' in value:
                    for category, items in value['catalogue'].items():
                        self.catalogue.replace(category, items)
                if value.get('reset_catalogue'):
                    self.catalogue.clear()
                    self.set_plan(Plan())
                if 'preset_path' in value:
                    try:
                        self.set_plan(Plan.load(value['preset_path']))
                    except Exception as exc:
                        messagebox.showerror('Preset progetto', str(exc))
                for path in value.get('updates', []):
                    self.add('update', path)
                if 'driver_path' in value:
                    self.add('driver', value['driver_path'])
                if value.get('show_components'):
                    self.select_page('Componenti')
                if value.get('inventory_errors'):
                    self.status.set('Lettura parziale. Tipi non disponibili: ' + ', '.join(value['inventory_errors']))
            self.catalogue.accept_applied(self.plan.operations[:self.completed()])
            self.render_plan()
            if self.project:
                self.editions['values'] = [f"{e['index']} — {e.get('name', 'Windows')}" for e in self.project.state.get('editions', [])]
                if not self.edition.get() and self.editions['values']:
                    self.edition.set(self.editions['values'][0])
            if kind == 'error':
                messagebox.showerror('Operazione fallita', value)
        self.poll_id = self.after(100, self.poll)

    def destroy(self):
        if hasattr(self, 'poll_id'):
            self.after_cancel(self.poll_id)
        super().destroy()

    def editable(self):
        if self.busy or (self.project and self.project.state.get('plan_hash')):
            messagebox.showwarning('Piano bloccato', 'Attendi il completamento. Se il piano e gia iniziato, riprendi lo stesso piano o scarta il montaggio.')
            return False
        return True

    def add(self, kind, value, **extra):
        if not self.editable():
            return
        op = dict(kind=kind, value=value, **extra)
        try:
            Plan(self.plan.operations + [op], self.plan.unattended).validate()
        except ValueError as exc:
            messagebox.showerror('Valore non valido', str(exc))
            return
        if op not in self.plan.operations:
            self.plan.operations.append(op)
        self.render_plan()

    def render_plan(self):
        if not hasattr(self, 'operations'):
            return
        self.operations.delete(*self.operations.get_children())
        completed = self.completed()
        for i, op in enumerate(self.plan.operations):
            value = SETTING_LABELS.get(op['value'], op['value'])
            if op['kind'] == 'service':
                value += f" | Start={op['start']}"
            self.operations.insert('', 'end', iid=str(i), values=(LABELS[op['kind']], value, 'Applicata' if i < completed else 'In attesa'))
        pending = max(0, len(self.plan.operations) - completed)
        self.pending_count.set(f'{pending} modifiche in attesa' if pending else 'Nessuna modifica in attesa')
        self.render_components()

    def render_components(self):
        if not hasattr(self, 'items'):
            return
        selected = {self.row_keys[i] for i in self.items.selection() if i in self.row_keys}
        for type_name, node in self.group_nodes.items():
            if self.items.exists(node):
                self.group_expansion[type_name] = self.items.item(node, 'open')
        self.items.delete(*self.items.get_children())
        self.row_keys = {}
        rows = self.catalogue.rows(self.plan, self.completed(), CATEGORIES.get(self.category.get()), self.search.get(),
                                   self.sort_column, self.sort_reverse, self.show_removed.get())
        grouped = defaultdict(list)
        for row in rows:
            grouped[row.type].append(row)
        parents = {}
        if self.grouped.get():
            for n, type_name in enumerate(sorted(grouped, key=natural, reverse=self.sort_reverse if self.sort_column == 'type' else False)):
                parents[type_name] = self.items.insert('', 'end', iid=f'g{n}', open=self.group_expansion.get(type_name, True), values=(f'{type_name} ({len(grouped[type_name])})', '', '', '', ''), tags=('group',))
        self.group_nodes = parents
        for i, row in enumerate(rows):
            iid = f'c{i}'
            self.row_keys[iid] = row.key
            tags = ('removed',) if row.removed else ('pending',) if row.pending else ()
            self.items.insert(parents.get(row.type, ''), 'end', iid=iid,
                              values=(row.type if not self.grouped.get() else '', row.name, row.projected, row.actual, row.pending), tags=tags)
            if row.key in selected:
                self.items.selection_add(iid)
        total = self.catalogue.rows(self.plan, self.completed(), show_removed=True)
        removed = sum(row.removed for row in total)
        self.summary.set(f'{len(rows)} visibili | {removed} rimozioni in attesa')
        titles = {'type': 'Tipo', 'name': 'Componente', 'projected': 'Stato previsto', 'actual': 'Stato immagine', 'pending': 'Modifica'}
        for column, title in titles.items():
            self.items.heading(column, text=title + (' v' if self.sort_reverse else ' ^') if column == self.sort_column else title)
        self.selection_changed()

    def sort_components(self, column):
        if self.busy:
            return
        self.sort_reverse = not self.sort_reverse if self.sort_column == column else False
        self.sort_column = column
        self.render_components()

    def selection_changed(self, event=None):
        keys = [self.row_keys[i] for i in self.items.selection() if i in self.row_keys]
        if keys:
            hint = 'Abilita, Disabilita o Rimuovi.' if all(key[0] == 'features' for key in keys) else 'Per pacchetti, applicazioni, capabilities e driver usa Rimuovi.'
            self.selection_info.set(f'{len(keys)} componenti selezionati | {hint}')
        else:
            self.selection_info.set('Seleziona un componente. I pulsanti disponibili dipendono dal tipo.')
        locked = self.busy or bool(self.project and self.project.state.get('plan_hash'))
        for action, button in self.action_buttons.items():
            allowed = bool(keys) and not locked and (action not in {'enable', 'disable'} or all(key[0] == 'features' for key in keys))
            if action == 'undo':
                allowed = allowed and any((OP_CATEGORY.get(op['kind']), op['value']) in keys for op in self.plan.operations)
            button.state(['!disabled'] if allowed else ['disabled'])
        self.details.configure(state='normal')
        self.details.delete('1.0', 'end')
        if len(keys) == 1:
            key = keys[0]
            metadata = self.catalogue.items[key].get('metadata', {})
            detail = 'Identita: ' + key[1]
            fields = [f'{k}: {v}' for k, v in metadata.items() if k in {'Version', 'Architecture', 'Release Type', 'Provider Name', 'Original File Name'}]
            self.details.insert('end', detail + '\n' + ' | '.join(fields))
        self.details.configure(state='disabled')

    def read_inventory(self, categories):
        result, errors = {}, []
        for category in categories:
            try:
                result[category] = self.project.list_items(category)
            except RuntimeError as exc:
                errors.append(CATEGORY_LABELS[category])
                self.tools.emit(f'Inventario non disponibile: {CATEGORY_LABELS[category]} — {exc}')
        if not result:
            raise RuntimeError('Nessuna categoria letta. Consultare il registro.')
        return {'catalogue': result, 'inventory_errors': errors}

    def load(self):
        if not self.project:
            return
        try:
            index = int(self.edition.get().split(' — ')[0])
        except ValueError:
            messagebox.showerror('Edizione', 'Seleziona un’edizione.')
            return
        self.tools.wimlib = self.wimlib.get()
        def operation():
            self.project.load_edition(index)
            return {**self.read_inventory(list(CATEGORY_LABELS)), 'show_components': True}
        self.execute(operation)

    def refresh_inventory(self):
        if not self.project or self.project.state.get('stage') != 'mounted':
            messagebox.showinfo('Carica un’edizione', 'Apri la ISO e carica un’edizione prima di leggere i componenti.')
            return
        category = CATEGORIES.get(self.category.get())
        categories = [category] if category else list(CATEGORY_LABELS)
        self.execute(lambda: self.read_inventory(categories))

    def queue_selected(self, action):
        if not self.editable():
            return
        keys = [self.row_keys[i] for i in self.items.selection() if i in self.row_keys]
        if not keys:
            return
        try:
            self.catalogue.edit(self.plan, keys, action)
        except ValueError as exc:
            messagebox.showerror('Operazione non disponibile', str(exc))
            return
        self.render_plan()
        count = len(self.plan.operations)
        self.status.set(f'Selezione aggiornata | {count} modifiche in attesa di Applica.' if count else 'Selezione ripristinata. Nessuna modifica in attesa.')

    def remove_queued(self):
        if not self.editable():
            return
        for index in sorted((int(i) for i in self.operations.selection()), reverse=True):
            self.plan.operations.pop(index)
        self.render_plan()
        self.status.set('Modifica annullata. Elenco componenti ripristinato.')

    def move(self, delta):
        selected = self.operations.selection()
        if len(selected) == 1 and self.editable():
            i = int(selected[0]); j = i + delta
            if 0 <= j < len(self.plan.operations):
                self.plan.operations[i], self.plan.operations[j] = self.plan.operations[j], self.plan.operations[i]
                self.render_plan()
                self.operations.selection_set(str(j))

    def discard(self):
        if self.project and messagebox.askyesno('Scarta modifiche', 'Scartare modifiche alla copia WIM, svuotare il piano e smontare?'):
            def operation():
                self.project.discard()
                return {'reset_catalogue': True}
            self.execute(operation)


def main():
    App().mainloop()
