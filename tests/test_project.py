from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import unittest
from unittest.mock import Mock, patch
from winimage.backend import ImageTools
from winimage.plan import Plan, unattended_xml, destructive_setup
from winimage.project import Project, editions, inventory


class SimulatedWindows(ImageTools):
    """Exercises production orchestration and DISM arguments; not real WIM/ISO validation."""
    def __init__(self):
        super().__init__(emit=lambda text: None)
        self.calls = []
        self.fail = None

    def extract_iso(self, image, destination):
        destination = Path(destination)
        for name in ('sources/install.esd', 'sources/boot.wim', 'boot/etfsboot.com', 'efi/microsoft/boot/efisys.bin'):
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'original-media')

    def dism(self, *args):
        self.calls.append(args)
        if self.fail and self.fail in args:
            raise RuntimeError('Simulated DISM failure')
        if '/Get-WimInfo' in args:
            if any(a.startswith('/Index:') for a in args):
                return 'Index : 6\nName : Windows Pro\nArchitecture : x64\n'
            return 'Index : 1\nName : Windows Home\nIndex : 6\nName : Windows Pro\n'
        if '/Export-Image' in args:
            path = next(a.split(':', 1)[1] for a in args if a.startswith('/DestinationImageFile:'))
            Path(path).write_bytes(b'exported-wim')
        if '/Get-MountedWimInfo' in args:
            return f'Mount Dir : {self.mount}\nImage File : {self.mount.parent / "working.wim"}\nStatus : Ok\n'
        if '/Get-Features' in args:
            return 'Feature Name : TelnetClient\nState : Disabled\nFeature Name : NetFx3\nState : Disabled with Payload Removed\n'
        return 'Operation completed successfully.'

    def run(self, args):
        self.calls.append(tuple(str(a) for a in args))
        if str(args[0]).endswith('oscdimg.exe'):
            Path(args[-1]).write_bytes(b'simulated-bootable-iso')
        return ''


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.iso = self.root / 'source.iso'
        self.iso.write_bytes(b'original-iso')
        self.exe = self.root / 'oscdimg.exe'
        self.exe.write_bytes(b'fixture')
        self.tools = SimulatedWindows()
        self.project = Project(self.root / 'project', self.tools)
        patcher = patch('winimage.project.shutil.disk_usage', return_value=Mock(free=200 * 1024**3))
        patcher.start()
        self.addCleanup(patcher.stop)

    def prepare(self):
        self.project.create(self.iso)
        self.project.load_edition(6)

    def test_full_iso_workflow_preserves_original_and_replaces_esd_automatically(self):
        self.prepare()
        self.assertEqual(self.project.list_items('features')[0]['name'], 'TelnetClient')
        self.project.apply(Plan([{'kind': 'feature_enable', 'value': 'TelnetClient'}], {'locale': 'it-IT'}))
        output = self.root / 'custom.iso'
        self.project.build(output, self.exe)
        self.assertEqual(self.iso.read_bytes(), b'original-iso')
        self.assertEqual(output.read_bytes(), b'simulated-bootable-iso')
        self.assertEqual((self.project.media / 'sources/install.wim').read_bytes(), b'exported-wim')
        self.assertFalse((self.project.media / 'sources/install.esd').exists())
        self.assertTrue((self.project.root / 'original-install/install.esd').is_file())
        self.assertTrue((self.project.media / 'autounattend.xml').is_file())
        self.assertEqual(self.project.state['stage'], 'exported')
        self.assertIsNone(self.tools.mount)

    def test_destination_existing_or_inside_project_is_rejected(self):
        self.prepare()
        self.project.apply(Plan())
        with self.assertRaises(ValueError):
            self.project.build(self.iso, self.exe)
        with self.assertRaises(ValueError):
            self.project.build(self.project.root / 'output.iso', self.exe)
        self.assertEqual(self.iso.read_bytes(), b'original-iso')

    def test_insufficient_space_fails_before_extraction(self):
        with patch('winimage.project.shutil.disk_usage', return_value=Mock(free=100)):
            with self.assertRaises(ValueError):
                self.project.create(self.iso)
        self.assertFalse(self.project.root.exists())

    def test_unknown_edition_does_not_export(self):
        self.project.create(self.iso)
        with self.assertRaises(ValueError):
            self.project.load_edition(3)
        self.assertFalse(self.project.working.exists())

    def test_all_local_inputs_checked_before_first_change(self):
        self.prepare()
        before = len(self.tools.calls)
        with self.assertRaises(ValueError):
            self.project.apply(Plan([{'kind': 'feature_enable', 'value': 'TelnetClient'}, {'kind': 'update', 'value': str(self.root / 'missing.cab')}]))
        self.assertEqual(len(self.tools.calls), before)

    def test_failure_retains_mount_and_records_only_completed_operations(self):
        self.prepare()
        plan = Plan([{'kind': 'feature_enable', 'value': 'TelnetClient'}, {'kind': 'feature_disable', 'value': 'NetFx3'}])
        self.tools.fail = '/Disable-Feature'
        with self.assertRaises(RuntimeError):
            self.project.apply(plan)
        self.assertEqual(self.project.state['completed'], 1)
        self.assertEqual(self.project.state['stage'], 'mounted')
        self.assertEqual(self.tools.mount, self.project.mount)
        with self.assertRaises(ValueError):
            self.project.apply(Plan())
        self.tools.fail = None
        self.project.apply(plan)
        self.assertEqual(sum('/Enable-Feature' in c for c in self.tools.calls), 1)
        self.assertEqual(self.project.state['stage'], 'committed')

    def test_reopen_validates_mount_ownership(self):
        self.prepare()
        reopened = Project.open(self.project.root, self.tools)
        self.assertEqual(reopened.mount, self.project.mount)
        self.tools.dism = Mock(return_value='Mount Dir : other\nStatus : Ok')
        with self.assertRaises(RuntimeError):
            Project.open(self.project.root, self.tools)

    def test_discard_resets_project_without_changing_source(self):
        self.prepare()
        self.project.discard()
        self.assertIsNone(self.tools.mount)
        self.assertFalse(self.project.working.exists())
        self.assertEqual(self.project.state['stage'], 'extracted')
        self.assertEqual(self.iso.read_bytes(), b'original-iso')

    def test_existing_answer_file_not_overwritten(self):
        self.prepare()
        answer = self.project.media / 'autounattend.xml'
        answer.write_text('original', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.project.apply(Plan(unattended={'locale': 'it-IT'}))
        self.assertEqual(answer.read_text(), 'original')

    def test_failed_iso_build_leaves_no_fake_final_output_and_can_retry(self):
        self.prepare()
        self.project.apply(Plan())
        output = self.root / 'custom.iso'
        original_run = self.tools.run
        self.tools.run = Mock(side_effect=RuntimeError('oscdimg failure'))
        with self.assertRaises(RuntimeError):
            self.project.build(output, self.exe)
        self.assertFalse(output.exists())
        self.assertEqual(self.project.state['stage'], 'committed')
        self.tools.run = original_run
        self.project.build(output, self.exe)
        self.assertTrue(output.is_file())


class PlanTests(unittest.TestCase):
    def test_protected_services_and_packages_are_rejected(self):
        for operation in ({'kind': 'service', 'value': 'RpcSs', 'start': 4},
                          {'kind': 'package_remove', 'value': 'Microsoft-Windows-ServicingStack-Package~test'},
                          {'kind': 'driver_remove', 'value': 'inbox.inf'}):
            with self.assertRaises(ValueError):
                Plan([operation]).validate()

    def test_shell_operators_in_setup_arguments_or_task_names_are_rejected(self):
        for operation in ({'kind': 'post_setup', 'value': 'app.exe', 'args': '/q & del C:\\*'},
                          {'kind': 'scheduled_task', 'value': 'task%PATH%', 'action': 'disable'}):
            with self.assertRaises(ValueError):
                Plan([operation]).validate()

    def test_preset_round_trip_and_version_check(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'preset.json'
            plan = Plan([{'kind': 'feature_enable', 'value': 'NetFx3'}])
            plan.save(path)
            self.assertEqual(Plan.load(path).to_dict(), plan.to_dict())
            path.write_text('{"version":99}', encoding='utf-8')
            with self.assertRaises(ValueError):
                Plan.load(path)

    def test_unattended_xml_architecture_and_non_destructive_settings(self):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(unattended_xml({'locale': 'it-IT'}, 'arm64'))
        ns = {'u': 'urn:schemas-microsoft-com:unattend'}
        self.assertTrue(all(c.attrib['processorArchitecture'] == 'arm64' for c in root.findall('.//u:component', ns)))
        self.assertIsNone(root.find('.//u:DiskConfiguration', ns))
        self.assertEqual(root.find('.//u:ComputerName', ns).text, 'WINIMAGE')

    def test_uefi_partitioning_requires_explicit_disk_and_wipe(self):
        import xml.etree.ElementTree as ET
        with self.assertRaises(ValueError):
            Plan(unattended={'disk_id': 0}).validate()
        config = {'disk_id': 2, 'wipe_disk': True}
        root = ET.fromstring(unattended_xml(config))
        ns = {'u': 'urn:schemas-microsoft-com:unattend'}
        self.assertEqual(root.find('.//u:WillWipeDisk', ns).text, 'true')
        self.assertEqual(root.find('.//u:InstallTo/u:DiskID', ns).text, '2')
        self.assertEqual(root.find('.//u:InstallTo/u:PartitionID', ns).text, '3')
        self.assertEqual(len(root.findall('.//u:CreatePartition', ns)), 3)
        self.assertTrue(destructive_setup(config))

    def test_imported_answer_file_is_validated_and_wipe_detected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'answer.xml'
            path.write_bytes(unattended_xml({'disk_id': 0, 'wipe_disk': True}))
            self.assertTrue(destructive_setup({'xml_path': str(path)}))
            self.assertEqual(unattended_xml({'xml_path': str(path)}), path.read_bytes())
            path.write_text('<wrong />')
            with self.assertRaises(ValueError):
                unattended_xml({'xml_path': str(path)})

    def test_registry_dword_range_and_unknown_hive(self):
        for operation in ({'kind': 'registry', 'value': 'Policy', 'hive': 'ONLINE', 'name': 'X', 'type': 'REG_DWORD', 'data': '1'},
                          {'kind': 'registry', 'value': 'Policy', 'hive': 'SOFTWARE', 'name': 'X', 'type': 'REG_DWORD', 'data': '-1'}):
            with self.assertRaises(ValueError):
                Plan([operation]).validate()


class RegistryTests(unittest.TestCase):
    def test_loaded_hive_is_unloaded_even_when_write_fails(self):
        with TemporaryDirectory() as directory:
            mount = Path(directory)
            hive = mount / 'Windows/System32/config/SOFTWARE'
            hive.parent.mkdir(parents=True)
            hive.write_bytes(b'fixture')
            tools = ImageTools(emit=lambda text: None)
            tools.mount = mount
            def execute(args):
                if 'add' in args:
                    raise RuntimeError('write failure')
                return ''
            tools.run = Mock(side_effect=execute)
            with self.assertRaises(RuntimeError):
                tools.offline_registry('SOFTWARE', 'Policy', 'Name', 1)
            calls = tools.run.call_args_list
            self.assertEqual(calls[-1].args[0][1], 'unload')

    def test_existing_setup_script_is_preserved(self):
        with TemporaryDirectory() as directory:
            tools = ImageTools(emit=lambda text: None)
            tools.mount = Path(directory)
            script = tools.mount / 'Windows/Setup/Scripts/SetupComplete.cmd'
            script.parent.mkdir(parents=True)
            script.write_text('echo existing\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                tools.setup_command('echo new')
            self.assertEqual(script.read_text(), 'echo existing\n')


if __name__ == '__main__':
    unittest.main()
