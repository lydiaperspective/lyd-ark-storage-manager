import contextlib
import io
import unittest

from lydstore import cli


class CliHelpTests(unittest.TestCase):
    def test_help_command_lists_available_top_level_commands(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = cli.main_run(["help"])

        self.assertEqual(result, 0)
        self.assertIn("layout", output.getvalue())
        self.assertIn("webui", output.getvalue())
        self.assertIn("help", output.getvalue())

    def test_help_command_can_show_nested_command(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = cli.main_run(["help", "webui"])

        self.assertEqual(result, 0)
        self.assertIn("setup", output.getvalue())
        self.assertIn("tailscale", output.getvalue())

    def test_unknown_top_level_command_prints_main_help(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            with self.assertRaises(SystemExit) as raised:
                cli.main_run(["not-a-command"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("usage: lydstore", output.getvalue())
        self.assertIn("webui", output.getvalue())
        self.assertIn("lydstore: error:", output.getvalue())

    def test_unknown_nested_command_prints_relevant_help(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            with self.assertRaises(SystemExit) as raised:
                cli.main_run(["webui", "not-a-command"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("usage: lydstore webui", output.getvalue())
        self.assertIn("setup", output.getvalue())
        self.assertIn("tailscale", output.getvalue())


if __name__ == "__main__":
    unittest.main()
