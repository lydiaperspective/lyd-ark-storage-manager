import unittest
from unittest.mock import call, patch

from lydstore import cli


class WebUICliTests(unittest.TestCase):
    @patch("lydstore.cli.config.load", return_value={})
    @patch("lydstore.cli.units.require_root")
    @patch("lydstore.cli.getpass.getpass", side_effect=["a-long-test-password-123", "a-long-test-password-123"])
    @patch("lydstore.web_auth.set_credentials")
    @patch("lydstore.cli.subprocess.run")
    def test_setup_saves_credentials_and_enables_service(
        self, run, set_credentials, getpass, require_root, load
    ):
        result = cli.main_run(["webui", "setup", "--username", "storage-admin"])

        self.assertEqual(result, 0)
        require_root.assert_called_once_with()
        set_credentials.assert_called_once_with("storage-admin", "a-long-test-password-123")
        run.assert_called_once_with(
            ["systemctl", "enable", "--now", "lydstore-web.service"], check=True
        )

    @patch("lydstore.cli.config.load", return_value={})
    @patch("lydstore.cli.units.require_root")
    @patch("lydstore.cli.shutil.which", return_value="/usr/bin/tailscale")
    @patch("lydstore.cli.subprocess.run")
    def test_tailscale_command_publishes_loopback_service(
        self, run, which, require_root, load
    ):
        result = cli.main_run(["webui", "tailscale"])

        self.assertEqual(result, 0)
        require_root.assert_called_once_with()
        which.assert_called_once_with("tailscale")
        run.assert_called_once_with(
            ["/usr/bin/tailscale", "serve", "--bg", "http://127.0.0.1:8765"],
            check=True,
        )

    @patch("lydstore.cli.config.load", return_value={})
    @patch("lydstore.cli.units.require_root")
    @patch("lydstore.cli.shutil.which", return_value=None)
    def test_tailscale_command_requires_tailscale(self, which, require_root, load):
        with self.assertRaisesRegex(RuntimeError, "Tailscale is not installed"):
            cli.main_run(["webui", "tailscale"])


if __name__ == "__main__":
    unittest.main()
