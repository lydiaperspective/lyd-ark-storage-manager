import unittest
from lydstore.units import drive_units, backup_units, valid_name

class UnitTests(unittest.TestCase):
    def test_drive_units_use_uuid_and_automount(self):
        units = drive_units({"name":"Archive","uuid":"1234-ABCD","uid":1000,"gid":1000,"fstype":"exfat","options":"defaults,nofail"})
        self.assertEqual(len(units), 2)
        self.assertIn("/dev/disk/by-uuid/1234-ABCD", units[0][1])
        self.assertIn("uid=1000,gid=1000,umask=0007", units[0][1])
        self.assertIn("WantedBy=multi-user.target", units[1][1])

    def test_invalid_names_rejected(self):
        with self.assertRaises(ValueError): valid_name("../escape")

    def test_backup_defaults_to_copy(self):
        units = backup_units({"name":"daily","user":"admin","source":"/ark/Share","destination":"gdrive:Backup","config":"/home/admin/.config/rclone/rclone.conf"})
        self.assertIn("rclone copy", units[0][1])

    def test_restore_is_copy_back_to_original_source(self):
        generated = backup_units({"name":"daily","user":"admin","source":"/ark/Share","destination":"gdrive:Backup","config":"/home/admin/.config/rclone/rclone.conf"})
        restore = next(content for name, content in generated if name.endswith("restore-daily.service"))
        self.assertIn("rclone copy", restore)
        self.assertIn('"gdrive:Backup" "/ark/Share"', restore)

    def test_sync_is_explicit(self):
        units = backup_units({"name":"mirror","user":"admin","source":"/ark/Share","destination":"gdrive:Backup","config":"/home/admin/.config/rclone/rclone.conf","mode":"sync"})
        self.assertIn("rclone sync", units[0][1])

if __name__ == "__main__": unittest.main()
