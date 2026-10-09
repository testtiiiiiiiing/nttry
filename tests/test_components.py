import unittest
from winimage.components import Catalogue
from winimage.plan import Plan
from winimage.project import inventory


class ComponentTests(unittest.TestCase):
    def setUp(self):
        self.catalogue = Catalogue()
        self.catalogue.replace('features', [{'name': 'Feature10', 'state': 'Enabled'}, {'name': 'Feature2', 'state': 'Disabled'}])
        self.catalogue.replace('packages', [{'name': 'Normal-Package', 'state': 'Installed', 'metadata': {'Release Type': 'Feature Pack'}},
                                            {'name': 'Package_for_ServicingStack_123', 'state': 'Installed'}])
        self.plan = Plan()

    def test_disable_immediately_changes_projected_state_and_keeps_real_state(self):
        self.catalogue.edit(self.plan, [('features', 'Feature10')], 'disable')
        row = next(row for row in self.catalogue.rows(self.plan) if row.key[1] == 'Feature10')
        self.assertEqual(row.projected, 'Disabilitato')
        self.assertEqual(row.actual, 'Abilitato')
        self.assertEqual(row.pending, 'Disabilitazione in attesa')

    def test_remove_disappears_and_can_be_shown_and_undone(self):
        key = ('packages', 'Normal-Package')
        self.catalogue.edit(self.plan, [key], 'remove')
        self.assertFalse(any(row.key == key for row in self.catalogue.rows(self.plan)))
        removed = next(row for row in self.catalogue.rows(self.plan, show_removed=True) if row.key == key)
        self.assertTrue(removed.removed)
        self.catalogue.edit(self.plan, [key], 'undo')
        restored = next(row for row in self.catalogue.rows(self.plan) if row.key == key)
        self.assertEqual(restored.projected, 'Installato')
        self.assertFalse(restored.pending)

    def test_inverse_edit_replaces_action_instead_of_adding_conflicts(self):
        key = ('features', 'Feature10')
        self.catalogue.edit(self.plan, [key], 'disable')
        self.catalogue.edit(self.plan, [key], 'remove')
        self.assertEqual(len(self.plan.operations), 1)
        self.assertEqual(self.plan.operations[0]['kind'], 'feature_remove')
        self.catalogue.edit(self.plan, [key], 'enable')
        self.assertEqual(self.plan.operations, [])

    def test_batch_validation_is_atomic_if_a_protected_component_is_selected(self):
        with self.assertRaises(ValueError):
            self.catalogue.edit(self.plan, [('packages', 'Normal-Package'), ('packages', 'Package_for_ServicingStack_123')], 'remove')
        self.assertEqual(self.plan.operations, [])
        self.assertEqual(len(self.catalogue.rows(self.plan)), 4)

    def test_disable_does_not_falsely_disable_packages(self):
        with self.assertRaises(ValueError):
            self.catalogue.edit(self.plan, [('packages', 'Normal-Package')], 'disable')
        self.assertFalse(self.plan.operations)

    def test_refresh_keeps_pending_edits(self):
        self.catalogue.edit(self.plan, [('features', 'Feature10')], 'disable')
        self.catalogue.replace('features', [{'name': 'Feature10', 'state': 'Enabled'}])
        row = self.catalogue.rows(self.plan, category='features')[0]
        self.assertEqual(row.projected, 'Disabilitato')
        self.assertEqual(row.actual, 'Abilitato')

    def test_name_sort_is_natural_and_type_sort_uses_package_release_type(self):
        features = self.catalogue.rows(self.plan, category='features', sort='name')
        self.assertEqual([r.name for r in features], ['Feature2', 'Feature10'])
        self.assertEqual([r.name for r in self.catalogue.rows(self.plan, category='features', sort='name', reverse=True)], ['Feature10', 'Feature2'])
        package = next(row for row in self.catalogue.rows(self.plan) if row.key[1] == 'Normal-Package')
        self.assertEqual(package.type, 'Componente opzionale')
        types = [row.type for row in self.catalogue.rows(self.plan)]
        self.assertEqual(types, sorted(types))

    def test_filter_searches_full_identity_not_just_friendly_name(self):
        self.catalogue.replace('appx', [{'name': 'Microsoft.App_2.0_x64__publisher', 'state': 'DisplayName'}])
        row = self.catalogue.rows(self.plan, search='publisher')[0]
        self.assertEqual(row.name, 'Microsoft.App')
        self.assertEqual(row.actual, 'Provisionata')

    def test_imported_plan_updates_projection_and_clearing_plan_restores_it(self):
        self.plan = Plan([{'kind': 'package_remove', 'value': 'Normal-Package'}])
        self.assertEqual(len(self.catalogue.rows(self.plan)), 3)
        self.plan.operations.clear()
        self.assertEqual(len(self.catalogue.rows(self.plan)), 4)

    def test_applied_removal_remains_hidden_after_dism_lists_absent_payload(self):
        op = {'kind': 'feature_remove', 'value': 'Feature10'}
        self.plan.operations.append(op)
        self.catalogue.accept_applied([op])
        self.catalogue.replace('features', [{'name': 'Feature10', 'state': 'Disabled with Payload Removed'}])
        self.assertFalse(self.catalogue.rows(self.plan, completed=1, category='features', show_removed=True))

    def test_only_completed_operations_change_actual_state(self):
        self.plan.operations.extend([{'kind': 'feature_disable', 'value': 'Feature10'}, {'kind': 'package_remove', 'value': 'Normal-Package'}])
        self.catalogue.accept_applied(self.plan.operations[:1])
        rows = self.catalogue.rows(self.plan, completed=1, show_removed=True)
        feature = next(row for row in rows if row.key[1] == 'Feature10')
        self.assertEqual(feature.actual, 'Disabilitato')
        self.assertFalse(feature.pending)
        package = next(row for row in rows if row.key[1] == 'Normal-Package')
        self.assertEqual(package.actual, 'Installato')
        self.assertEqual(package.pending, 'Rimozione in attesa')

    def test_appx_metadata_before_package_name_and_release_type_are_parsed(self):
        appx = inventory('DisplayName : Microsoft.App\nVersion : 2.0\nArchitecture : x64\nPackageName : App_2.0_x64__abc\n\n', 'PackageName', 'DisplayName')
        self.assertEqual(appx[0]['metadata']['DisplayName'], 'Microsoft.App')
        self.assertEqual(appx[0]['metadata']['Version'], '2.0')
        packages = inventory('Package Identity : Package-X\nState : Installed\nRelease Type : Security Update\n\nPackage Identity : Package-Y\nState : Staged\nRelease Type : Feature Pack', 'Package Identity')
        self.catalogue.replace('packages', packages)
        self.assertEqual({row.type for row in self.catalogue.rows(Plan(), category='packages')}, {'Aggiornamento sicurezza', 'Componente opzionale'})


if __name__ == '__main__':
    unittest.main()
