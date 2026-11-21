import json
import tempfile
import unittest
from pathlib import Path
from lydstore.web_auth import set_credentials, verify_credentials, credentials_configured

class WebAuthTests(unittest.TestCase):
    def test_credentials_are_hashed_and_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "webui.json"
            set_credentials("storage-admin", "a-long-test-password-123", path)
            payload = json.loads(path.read_text())
            self.assertNotIn("a-long-test-password-123", path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertTrue(credentials_configured(path))
            self.assertTrue(verify_credentials("storage-admin", "a-long-test-password-123", path))
            self.assertFalse(verify_credentials("storage-admin", "wrong-password", path))
            self.assertFalse(verify_credentials("another-user", "a-long-test-password-123", path))

    def test_username_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                set_credentials("../root", "a-long-test-password-123", Path(directory) / "webui.json")

    def test_short_password_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                set_credentials("admin", "short", Path(directory) / "webui.json")

if __name__ == "__main__":
    unittest.main()
