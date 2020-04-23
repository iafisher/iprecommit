import unittest
from io import StringIO

from precommitlib import lib, checks


class Test(unittest.TestCase):
    def setUp(self):
        lib.turn_off_colors()
        checklist = lib.Checklist()
        checklist.check(checks.NoStagedAndUnstagedChanges())
        checklist.check(checks.NoWhitespaceInFilePath())
        checklist.check(checks.PythonFormat())

        self.mock_console = MockConsole()
        self.mock_fs = MockFilesystem()
        self.precommit = lib.Precommit(
            checklist.checks,
            console=self.mock_console,
            fs=self.mock_fs,
            check_all=True,
            dry_run=False,
        )

    def test_check_command(self):
        self.precommit.check()

        output = self.mock_console.captured_output.getvalue()
        self.assertEqual(
            output.strip(),
            multiline(
                """
            [NoStagedAndUnstagedChanges] error: unstaged changes to a staged file

              test_repo/bad_python_format.py

            [NoWhitespaceInFilePath] passed!
            [PythonFormat] error: bad formatting

              would reformat test_repo/bad_python_format.py
              All done! 💥 💔 💥
              1 file would be reformatted.


            Ran 3 checks. Detected 2 issues. Fix all of them with 'precommit fix'.
        """
            ),
        )

    def test_fix_command(self):
        self.precommit.fix()

        output = self.mock_console.captured_output.getvalue()
        self.assertEqual(
            output.strip(),
            multiline(
                """
            [NoStagedAndUnstagedChanges] fixing
            [PythonFormat] fixing

            Ran 2 fixable checks. Detected 2 issues. Fixed 2 of them.
        """
            ),
        )
        self.assertEqual(
            self.mock_fs.commands_run,
            [
                ["git", "add", "test_repo/bad_python_format.py"],
                ["black", "test_repo/bad_python_format.py"],
                ["git", "add", "test_repo/bad_python_format.py"],
            ],
        )


class MockConsole(lib.Console):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.captured_output = StringIO()

    def _print(self, *args, **kwargs):
        self.printed_anything_yet = True
        print(*args, file=self.captured_output, **kwargs)


class MockFilesystem:
    def __init__(self):
        self.commands_run = []

    def stage_files(self, files):
        self.run(["git", "add"] + files)

    def get_staged_files(self):
        return ["test_repo/bad_python_format.py"]

    def get_staged_for_deletion_files(self):
        return []

    def get_unstaged_files(self):
        return ["test_repo/bad_python_format.py"]

    def run(self, cmd):
        self.commands_run.append(cmd)


def multiline(s):
    # Can't use textwrap.dedent because it doesn't ignore blank lines.
    leading_ws = 999
    for line in s.splitlines():
        if not line:
            continue

        for i, c in enumerate(line):
            if not c.isspace():
                leading_ws = min(i, leading_ws)
                break

    return ("\n".join(l[leading_ws:] if l else l for l in s.splitlines())).strip()


if __name__ == "__main__":
    unittest.main()
