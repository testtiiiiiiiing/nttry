"""Real Tk interactions; skipped only when the runner has no desktop/display."""
import os
import unittest
from winimage.app import App
from winimage.plan import Plan


@unittest.skipUnless(os.name == 'nt' or os.environ.get('DISPLAY'), 'Desktop Tk o display virtuale richiesto')
class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.app = App()
        self.app.withdraw()
        self.addCleanup(self.app.destroy)
        self.app.catalogue.replace('features', [{'name': 'Feature10', 'state': 'Enabled'}, {'name': 'Feature2', 'state': 'Disabled'}])
        self.app.catalogue.replace('packages', [{'name': 'Normal-Package', 'state': 'Installed'}])
        self.app.render_components()

    def select(self, key):
        row = next(i for i, k in self.app.row_keys.items() if k == key)
        self.app.items.selection_set(row)
        self.app.selection_changed()
        return row

    def test_disable_button_changes_row_and_adds_one_pending_operation(self):
        self.select(('features', 'Feature10'))
        self.app.action_buttons['disable'].invoke()
        row = self.select(('features', 'Feature10'))
        values = self.app.items.item(row, 'values')
        self.assertEqual(values[2:5], ('Disabilitato', 'Abilitato', 'Disabilitazione in attesa'))
        self.assertEqual(len(self.app.operations.get_children()), 1)

    def test_remove_button_hides_row_and_undo_from_queue_restores_it(self):
        key = ('packages', 'Normal-Package')
        self.select(key)
        self.app.action_buttons['remove'].invoke()
        self.assertNotIn(key, self.app.row_keys.values())
        self.app.operations.selection_set('0')
        self.app.remove_queued()
        self.assertIn(key, self.app.row_keys.values())
        self.assertFalse(self.app.plan.operations)

    def test_show_removed_and_undo_button(self):
        key = ('features', 'Feature10')
        self.select(key)
        self.app.action_buttons['remove'].invoke()
        self.app.show_removed.set(True)
        self.app.render_components()
        row = self.select(key)
        self.assertEqual(self.app.items.item(row, 'values')[2], 'Rimosso')
        self.app.action_buttons['undo'].invoke()
        row = self.select(key)
        self.assertEqual(self.app.items.item(row, 'values')[2], 'Abilitato')

    def test_package_disable_button_is_disabled_and_group_selection_is_safe(self):
        self.select(('packages', 'Normal-Package'))
        self.assertTrue(self.app.action_buttons['disable'].instate(['disabled']))
        self.app.items.selection_set('g0')
        self.app.selection_changed()
        self.assertTrue(self.app.action_buttons['remove'].instate(['disabled']))

    def test_refresh_payload_keeps_projection_and_sort_changes_order(self):
        types = [self.app.items.item(i, 'values')[0] for i in self.app.items.get_children()]
        self.app.sort_components('type')
        self.assertEqual([self.app.items.item(i, 'values')[0] for i in self.app.items.get_children()], types[::-1])
        self.select(('features', 'Feature10'))
        self.app.action_buttons['disable'].invoke()
        self.app.catalogue.replace('features', [{'name': 'Feature10', 'state': 'Enabled'}, {'name': 'Feature2', 'state': 'Disabled'}])
        self.app.grouped.set(False)
        self.app.category.set('Funzionalita')
        self.app.sort_components('name')
        self.assertEqual([self.app.items.item(i, 'values')[1] for i in self.app.items.get_children()], ['Feature2', 'Feature10'])
        self.assertEqual(self.app.items.item(self.select(('features', 'Feature10')), 'values')[2], 'Disabilitato')
        self.app.sort_components('name')
        self.assertEqual([self.app.items.item(i, 'values')[1] for i in self.app.items.get_children()], ['Feature10', 'Feature2'])

    def test_loading_preset_updates_component_rows(self):
        self.app.set_plan(Plan([{'kind': 'package_remove', 'value': 'Normal-Package'}, {'kind': 'feature_disable', 'value': 'Feature10'}]))
        self.assertNotIn(('packages', 'Normal-Package'), self.app.row_keys.values())
        self.assertEqual(self.app.items.item(self.select(('features', 'Feature10')), 'values')[2], 'Disabilitato')
        self.app.set_plan(Plan())
        self.assertIn(('packages', 'Normal-Package'), self.app.row_keys.values())


if __name__ == '__main__':
    unittest.main()
