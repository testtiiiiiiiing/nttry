from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import unittest
from unittest.mock import Mock
from winimage.backend import ImageTools


class ImageToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root / "original image.wim"
        self.image.write_bytes(b"test fixture")
        self.tools = ImageTools(emit=lambda text: None)
        self.tools.dism = Mock(return_value="ok")

    def test_mount_and_commit_use_offline_image(self):
        mount = self.root / "mount"
        self.tools.mount_image(self.image, 2, mount)
        self.tools.dism.assert_called_with("/Mount-Image", f"/ImageFile:{self.image}", "/Index:2", f"/MountDir:{mount}", "/CheckIntegrity")
        self.tools.service("/Get-Packages")
        self.tools.dism.assert_called_with(f"/Image:{mount}", "/Get-Packages")
        self.tools.unmount(True)
        self.tools.dism.assert_called_with("/Unmount-Image", f"/MountDir:{mount}", "/Commit")
        self.assertIsNone(self.tools.mount)

    def test_failed_mount_does_not_record_active_mount(self):
        self.tools.dism.side_effect = RuntimeError("DISM failure")
        with self.assertRaises(RuntimeError):
            self.tools.mount_image(self.image, 1, self.root / "mount")
        self.assertIsNone(self.tools.mount)

    def test_failed_commit_preserves_mount_for_recovery(self):
        self.tools.mount = self.root / "mount"
        self.tools.dism.side_effect = RuntimeError("DISM failure")
        with self.assertRaises(RuntimeError):
            self.tools.unmount(True)
        self.assertIsNotNone(self.tools.mount)

    def test_nonempty_mount_directory_is_rejected(self):
        with self.assertRaises(ValueError):
            self.tools.mount_image(self.image, 1, self.root)
        self.tools.dism.assert_not_called()

    def test_servicing_without_mount_is_rejected(self):
        with self.assertRaises(ValueError):
            self.tools.feature("NetFx3", True)
        self.tools.dism.assert_not_called()

    def test_export_never_overwrites_original(self):
        with self.assertRaises(ValueError):
            self.tools.export(self.image, 1, self.image)
        self.assertEqual(self.image.read_bytes(), b"test fixture")
        self.tools.dism.assert_not_called()

    def test_esd_export_uses_integrity_check(self):
        esd = self.root / "install.esd"
        esd.write_bytes(b"fixture")
        output = self.root / "copy.wim"
        self.tools.export(esd, 1, output)
        self.tools.dism.assert_called_with("/Export-Image", f"/SourceImageFile:{esd}", "/SourceIndex:1", f"/DestinationImageFile:{output}", "/Compress:max", "/CheckIntegrity")

    def test_command_arguments_are_not_executed_by_shell(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, "success"))
        tools = ImageTools(emit=lambda text: None, runner=runner)
        tools.run(["tool.exe", "name & other"])
        self.assertEqual(runner.call_args.args[0], ["tool.exe", "name & other"])
        self.assertNotIn("shell", runner.call_args.kwargs)

    def test_failure_and_reboot_exit_codes(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 3010, "restart"))
        tools = ImageTools(emit=lambda text: None, runner=runner)
        tools.run(["tool"])
        runner.return_value = subprocess.CompletedProcess([], 5, "denied")
        with self.assertRaises(RuntimeError):
            tools.run(["tool"])

    def test_iso_requires_both_boot_files_and_external_output(self):
        source = self.root / "media"
        for file in ("boot/etfsboot.com", "efi/microsoft/boot/efisys.bin", "sources/boot.wim"):
            path = source / file
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
        exe = self.root / "oscdimg.exe"
        exe.write_bytes(b"fixture")
        self.tools.run = Mock()
        with self.assertRaises(ValueError):
            self.tools.build_iso(source, source / "output.iso", exe)
        output = self.root / "output.iso"
        self.tools.build_iso(source, output, exe)
        args = self.tools.run.call_args.args[0]
        self.assertIn("-bootdata:2#p0,e,b" + str(source / "boot/etfsboot.com") + "#pEF,e,b" + str(source / "efi/microsoft/boot/efisys.bin"), args)
        self.assertEqual(args[-1], output)


if __name__ == "__main__":
    unittest.main()
