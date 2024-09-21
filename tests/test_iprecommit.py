import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from iprecommit.checks import Exclude, Include, _filter_paths


owndir = Path(__file__).absolute().parent


class Base(unittest.TestCase):
    def setUp(self):
        self.tmpdir_obj = tempfile.TemporaryDirectory()
        self.tmpdir = self.tmpdir_obj.name
        print(f"test: created temporary dir: {self.tmpdir}")

    def tearDown(self):
        self.tmpdir_obj.cleanup()

    def _create_repo(self, precommit=None, install_hook=True):
        os.chdir(self.tmpdir)

        run_shell(["git", "init"])
        print("test: initialized git repo")

        run_shell(["python3", "-m", "venv", ".venv"])
        print("test: created virtualenv")

        run_shell([".venv/bin/pip", "install", str(owndir.parent)])
        print("test: installed iprecommit library")

        if precommit is None:
            run_shell([".venv/bin/iprecommit", "template"])
            assert Path("precommit.py").exists()
            print("test: created precommit.py template")
        else:
            shutil.copy(os.path.join(owndir, precommit), "precommit.py")

        if install_hook:
            run_shell([".venv/bin/iprecommit", "install"])
            print("test: installed pre-commit hook")


class TestEndToEnd(Base):
    def test_failed_precommit_run(self):
        self._create_repo()

        copy_and_stage_file("assets/includes_do_not_submit.txt")
        proc = run_shell(
            [".venv/bin/iprecommit", "run"], check=False, capture_stdout=True
        )
        expected_stdout = textwrap.dedent(
            """\
        iprecommit: NoDoNotSubmit: running
        iprecommit: NoDoNotSubmit: failed
        iprecommit: NewlineAtEndOfFile: running
        iprecommit: NewlineAtEndOfFile: passed

        1 failed. Commit aborted.
        """
        )
        self.assertEqual(proc.stdout, expected_stdout)
        self.assertNotEqual(proc.returncode, 0)

    def test_not_in_git_root(self):
        self._create_repo()

        copy_and_stage_file("assets/includes_do_not_submit.txt")

        other_dir = os.path.join(self.tmpdir, "tmp")
        os.mkdir(other_dir)
        os.chdir(other_dir)

        proc = run_shell(
            ["../.venv/bin/iprecommit", "run"], check=False, capture_stdout=True
        )
        expected_stdout = textwrap.dedent(
            """\
        iprecommit: NoDoNotSubmit: running
        iprecommit: NoDoNotSubmit: failed
        iprecommit: NewlineAtEndOfFile: running
        iprecommit: NewlineAtEndOfFile: passed

        1 failed. Commit aborted.
        """
        )
        self.assertEqual(proc.stdout, expected_stdout)
        self.assertNotEqual(proc.returncode, 0)

    def test_failed_unstaged_precommit_run(self):
        self._create_repo()
        p = Path("example.txt")
        commit_file(p, "...\n")
        p.write_text("DO NOT SUBMIT")

        proc = run_shell(
            [".venv/bin/iprecommit", "run", "--unstaged"],
            check=False,
            capture_stdout=True,
        )
        expected_stdout = textwrap.dedent(
            """\
        iprecommit: NoDoNotSubmit: running
        iprecommit: NoDoNotSubmit: failed
        iprecommit: NewlineAtEndOfFile: running
        iprecommit: NewlineAtEndOfFile: failed

        2 failed. Commit aborted.
        """
        )
        self.assertEqual(proc.stdout, expected_stdout)
        self.assertNotEqual(proc.returncode, 0)

    def test_failed_git_commit(self):
        self._create_repo()
        pre_commit_script = Path(".git/hooks/pre-commit").read_text()
        self.assertEqual(
            pre_commit_script,
            textwrap.dedent(
                """\
                #!/bin/sh

                set -e
                .venv/bin/iprecommit run
                """
            )
            % dict(tmpdir=self.tmpdir),
        )

        copy_and_stage_file("assets/includes_do_not_submit.txt")
        proc = run_shell(["git", "commit", "-m", "."], check=False, capture_stderr=True)
        expected_stderr = textwrap.dedent(
            """\
        iprecommit: NoDoNotSubmit: running
        iprecommit: NoDoNotSubmit: failed
        iprecommit: NewlineAtEndOfFile: running
        iprecommit: NewlineAtEndOfFile: passed

        1 failed. Commit aborted.
        """
        )
        self.assertEqual(proc.stderr, expected_stderr)
        self.assertNotEqual(proc.returncode, 0)

    def test_run_fix(self):
        self._create_repo(precommit="assets/precommit_no_typos.py")

        p = Path("example.txt")
        commit_file(p, "...\n")
        p.write_text("programing\n")

        run_shell(["git", "add", str(p)])
        proc = run_shell([".venv/bin/iprecommit", "fix"], capture_stdout=True)
        expected_stdout = textwrap.dedent(
            """\
        iprecommit: NoTypos: fixing
        iprecommit: NoTypos: finished
        """
        )
        self.assertEqual(proc.stdout, expected_stdout)
        self.assertEqual(proc.returncode, 0)

        self.assertEqual(p.read_text(), "programming\n")

    def test_intrinsic_include_pattern(self):
        self.ensure_black_is_installed()

        self._create_repo(precommit="assets/precommit_python_format.py")

        p = Path("example.txt")
        p.write_text("This does not parse as valid Python code.\n")
        run_shell(["git", "add", str(p)])

        proc = run_shell(
            [".venv/bin/iprecommit", "run"], check=False, capture_stdout=True
        )
        expected_stdout = textwrap.dedent(
            """\
            iprecommit: PythonFormat: skipped
            """
        )
        self.assertEqual(proc.stdout, expected_stdout)
        self.assertEqual(proc.returncode, 0)

    def test_uninstall(self):
        self._create_repo()
        self.assertTrue(Path(".git/hooks/pre-commit").exists())
        run_shell([".venv/bin/iprecommit", "uninstall"])
        self.assertFalse(Path(".git/hooks/pre-commit").exists())

    def test_inline_command(self):
        self.ensure_black_is_installed()

        self._create_repo(precommit="assets/precommit_inline_command.py")

        copy_and_stage_file("assets/bad_python_format.py")

        proc = run_shell([".venv/bin/iprecommit", "run"], check=False, capture_stdout=True)
        expected_stdout = textwrap.dedent(
            """\
            iprecommit: black --check: running
            iprecommit: black --check: failed

            1 failed. Commit aborted.
            """
        )
        self.assertEqual(proc.stdout, expected_stdout)
        self.assertEqual(proc.returncode, 1)

    def test_install_does_not_overwrite(self):
        self._create_repo(install_hook=False)

        Path(".git/hooks/pre-commit").write_text("...\n")

        proc = run_shell([".venv/bin/iprecommit", "install"], check=False, capture_stderr=True)
        self.assertEqual(proc.stderr, "Error: pre-commit hook already exists. Re-run with --force to overwrite.\n")
        self.assertEqual(proc.returncode, 1)

        run_shell([".venv/bin/iprecommit", "install", "--force"])
        self.assertIn("iprecommit", Path(".git/hooks/pre-commit").read_text())

    def test_template_does_not_overwrite(self):
        self._create_repo(precommit="assets/precommit_inline_command.py")

        proc = run_shell([".venv/bin/iprecommit", "template"], check=False, capture_stderr=True)
        self.assertEqual(proc.stderr, "Error: precommit.py already exists. Re-run with --force to overwrite.\n")
        self.assertEqual(proc.returncode, 1)

    # TODO: init and install as one command?
    # TODO: test uninstall will check for iprecommit
    # TODO: customize hook location
    # TODO: pass_files=True, separately=True

    def ensure_black_is_installed(self):
        self.assertIsNotNone(
            shutil.which("black"),
            msg="This test requires the `black` executable to be installed.",
        )


class TestUnit(unittest.TestCase):
    def test_changes_filter(self):
        self.assertEqual(_filter_paths(["a.py", "b.txt"], "*.py", []), ["a.py"])
        self.assertEqual(_filter_paths(["a.py", "b.txt"], "*.txt", []), ["b.txt"])

        self.assertEqual(
            _filter_paths(["a.py", "b.txt", "c.py"], "*.py", [Exclude("c.py")]),
            ["a.py"],
        )

        self.assertEqual(
            _filter_paths(
                ["a.py", "b.txt", "c.py"],
                "*.py",
                [Exclude("c.py"), Include("b.txt")],
            ),
            ["a.py", "b.txt"],
        )


def copy_and_stage_file(p):
    name = os.path.basename(p)
    shutil.copy(os.path.join(owndir, p), name)
    run_shell(["git", "add", name])


def commit_file(p, contents):
    p.write_text(contents)
    run_shell(["git", "add", str(p)])
    run_shell(["git", "commit", "-m", "."])


def run_shell(args, check=True, capture_stdout=False, capture_stderr=False):
    print(f"test: running {args}")
    return subprocess.run(
        args,
        check=check,
        stdout=subprocess.PIPE if capture_stdout else None,
        stderr=subprocess.PIPE if capture_stderr else None,
        text=capture_stdout or capture_stderr,
    )


if __name__ == "__main__":
    unittest.main()
