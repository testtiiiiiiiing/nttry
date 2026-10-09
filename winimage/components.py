"""Component catalogue and projected edits, independent of GUI and DISM."""
from dataclasses import dataclass
import re
from .plan import Plan

CATEGORY_LABELS = {'features': 'Funzionalita', 'packages': 'Pacchetti Windows',
                   'appx': 'Applicazioni', 'capabilities': 'Capabilities', 'drivers': 'Driver'}
OP_CATEGORY = {'feature_enable': 'features', 'feature_disable': 'features', 'feature_remove': 'features',
               'package_remove': 'packages', 'appx_remove': 'appx', 'capability_remove': 'capabilities', 'driver_remove': 'drivers'}
REMOVE_KINDS = {kind for kind in OP_CATEGORY if kind.endswith('_remove')}
STATE_LABELS = {'Enabled': 'Abilitato', 'Disabled': 'Disabilitato',
                'Disabled with Payload Removed': 'Disabilitato, payload assente',
                'Installed': 'Installato', 'Staged': 'Preparato', 'Not Present': 'Assente',
                'Install Pending': 'Installazione al riavvio', 'Uninstall Pending': 'Rimozione al riavvio',
                'Superseded': 'Sostituito', 'Provisioned': 'Provisionata', 'Removed': 'Rimosso'}
RELEASE_LABELS = {'Security Update': 'Aggiornamento sicurezza', 'Update': 'Aggiornamento',
                  'Feature Pack': 'Componente opzionale', 'Language Pack': 'Lingua',
                  'Foundation': 'Sistema', 'Service Pack': 'Service pack'}


def natural(value):
    return tuple((1, int(piece)) if piece.isdigit() else (0, piece.casefold())
                 for piece in re.split(r'(\d+)', str(value)))


def component_type(category, item):
    meta = item.get('metadata', {})
    if category == 'packages':
        release = meta.get('Release Type', '')
        if release in RELEASE_LABELS:
            return RELEASE_LABELS[release]
        name = item['name'].lower()
        if 'servicingstack' in name:
            return 'Manutenzione Windows'
        if 'rollupfix' in name:
            return 'Aggiornamento cumulativo'
        if 'fod' in name:
            return 'Componente opzionale'
        if 'languagepack' in name:
            return 'Lingua'
        return release or 'Pacchetto Windows'
    if category == 'drivers':
        return 'Driver / ' + meta['Class Name'] if meta.get('Class Name') else 'Driver'
    return CATEGORY_LABELS[category]


def display_name(category, item):
    meta = item.get('metadata', {})
    if category == 'appx':
        return meta.get('DisplayName') or item['name'].split('_')[0]
    if category == 'drivers':
        return meta.get('Original File Name') or item['name']
    if category == 'packages':
        name = item['name'].split('~')[0]
        return re.sub(r'^(Microsoft-Windows-|Package_for_)', '', name)
    return item['name']


@dataclass(frozen=True)
class Component:
    key: tuple
    name: str
    type: str
    actual: str
    projected: str
    pending: str
    removed: bool
    metadata: dict


class Catalogue:
    def __init__(self):
        self.items = {}
        self.loaded = set()
        self.applied_removals = set()

    def clear(self):
        self.items.clear()
        self.loaded.clear()
        self.applied_removals.clear()

    def replace(self, category, items):
        if category not in CATEGORY_LABELS:
            raise ValueError('Categoria non supportata.')
        self.items = {key: value for key, value in self.items.items() if key[0] != category}
        for item in items:
            record = dict(item)
            if category == 'appx':
                record['state'] = 'Provisioned'
            elif category == 'drivers':
                record['state'] = 'Installed'
            self.items[(category, item['name'])] = record
        self.loaded.add(category)

    def accept_applied(self, operations):
        for op in operations:
            category = OP_CATEGORY.get(op['kind'])
            key = (category, op['value'])
            if not category:
                continue
            if op['kind'] in REMOVE_KINDS:
                self.applied_removals.add(key)
            elif key in self.items:
                self.items[key]['state'] = 'Enabled' if op['kind'] == 'feature_enable' else 'Disabled'

    def rows(self, plan, completed=0, category=None, search='', sort='type', reverse=False, show_removed=False):
        pending = {(OP_CATEGORY[op['kind']], op['value']): op['kind']
                   for op in plan.operations[completed:] if op['kind'] in OP_CATEGORY}
        rows = []
        query = search.casefold().strip()
        for key, item in self.items.items():
            if key in self.applied_removals or (category and key[0] != category):
                continue
            op = pending.get(key)
            removed = op in REMOVE_KINDS
            if removed and not show_removed:
                continue
            actual = STATE_LABELS.get(item.get('state', ''), item.get('state', ''))
            if op == 'feature_enable':
                projected, change = 'Abilitato', 'Abilitazione in attesa'
            elif op == 'feature_disable':
                projected, change = 'Disabilitato', 'Disabilitazione in attesa'
            elif removed:
                projected, change = 'Rimosso', 'Rimozione in attesa'
            else:
                projected, change = actual, ''
            row = Component(key, display_name(key[0], item), component_type(key[0], item), actual,
                            projected, change, removed, item.get('metadata', {}))
            if query and query not in ' '.join((row.name, key[1], row.type, row.actual, row.projected, row.pending)).casefold():
                continue
            rows.append(row)
        if sort not in {'name', 'type', 'actual', 'projected', 'pending'}:
            raise ValueError('Colonna non ordinabile.')
        return sorted(rows, key=lambda row: (natural(getattr(row, sort)), natural(row.name), natural(row.key[1])), reverse=reverse)

    def edit(self, plan, keys, action):
        if action not in {'enable', 'disable', 'remove', 'undo'}:
            raise ValueError('Azione non supportata.')
        keys = set(keys)
        if not keys or not keys <= self.items.keys():
            raise ValueError('Selezionare componenti presenti nell’inventario.')
        if any(key in self.applied_removals for key in keys):
            raise ValueError('Una rimozione gia applicata non si annulla dalla coda.')
        if action in {'enable', 'disable'} and any(key[0] != 'features' for key in keys):
            raise ValueError('Abilita e Disabilita sono disponibili solo per le funzionalita Windows. Per pacchetti, app, capabilities e driver usare Rimuovi.')
        replacement = [dict(op) for op in plan.operations if (OP_CATEGORY.get(op['kind']), op['value']) not in keys]
        for category, name in sorted(keys):
            if action == 'undo':
                continue
            state = self.items[(category, name)].get('state')
            if action == 'enable' and state == 'Enabled':
                continue
            if action == 'disable' and state in {'Disabled', 'Disabled with Payload Removed'}:
                continue
            kind = 'feature_' + action if category == 'features' else next(k for k, c in OP_CATEGORY.items() if c == category)
            replacement.append({'kind': kind, 'value': name})
        # Validate the whole batch before changing either the plan or its projection.
        Plan(replacement, plan.unattended).validate()
        plan.operations[:] = replacement
