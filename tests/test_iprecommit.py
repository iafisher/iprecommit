import os
import platform
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from iprecommit import lib


owndir = Path(__file__).absolute().parent


class Base(unittest.TestCase):
    def setUp(self):
        os.chdir(self.tmpdir)
        for path in os.listdir():
            if path != ".venv":
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)

    @classmethod
    def setUpClass(cls):
        cls.tmpdir_obj = tempfile.TemporaryDirectory()
        cls.tmpdir = cls.tmpdir_obj.name
        print(f"test: created temporary dir: {cls.tmpdir}")

        os.chdir(cls.tmpdir)

        run_shell(["python3", "-m", "venv", ".venv"])
        print("test: created virtualenv")

        run_shell([".venv/bin/pip", "install", str(owndir.parent)])
        # modify PATH because the precommit.toml template uses the unqualified names of iprecommit commands
        os.environ["PATH"] += os.pathsep + cls.tmpdir + "/.venv/bin"
        print("test: installed iprecommit and iprecommit-extra libraries")

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir_obj.cleanup()

    def _create_repo(self, precommit_text=None, install_hook=True, path=None):
        os.chdir(self.tmpdir)

        run_shell(["git", "init"])
        print("test: initialized git repo")

        if precommit_text is not None:
            Path("precommit.toml").write_text(precommit_text)

        if install_hook:
            run_shell(
                [".venv/bin/iprecommit", "install"]
                + (["--path", path] if path is not None else [])
            )
            print("test: installed pre-commit hook")


class TestEndToEnd(Base):
    def test_failed_precommit_run(self):
        self._create_repo()
        stage_do_not_submit_file()

        proc = iprecommit_run()
        print(repr(proc.stdout))
        expected_stdout = S(
            """\
            [iprecommit] NoForbiddenStrings: running
            includes_do_not_submit.txt
            [iprecommit] NoForbiddenStrings: failed


            [iprecommit] NewlineAtEndOfFile: running
            [iprecommit] NewlineAtEndOfFile: passed


            1 failed. Commit aborted.
            """
        )
        self.assertEqual(proc.stdout, expected_stdout)
        self.assertNotEqual(proc.returncode, 0)

    def test_not_in_git_root(self):
        self._create_repo()
        stage_do_not_submit_file()

        other_dir = os.path.join(self.tmpdir, "tmp")
        os.mkdir(other_dir)
        os.chdir(other_dir)

        proc = run_shell(
            ["../.venv/bin/iprecommit", "run"], check=False, capture_stdout=True
        )
        expected_stdout = S(
            """\
            [iprecommit] NoForbiddenStrings: running
            includes_do_not_submit.txt
            [iprecommit] NoForbiddenStrings: failed


            [iprecommit] NewlineAtEndOfFile: running
            [iprecommit] NewlineAtEndOfFile: passed


            1 failed. Commit aborted.
            """
        )
        self.assertEqual(proc.stdout, expected_stdout)
        self.assertNotEqual(proc.returncode, 0)

    def test_failed_unstaged_precommit_run(self):
        self._create_repo()
        p = Path("example.txt")
        create_and_commit_file(p, "...\n")
        p.write_text("DO NOT " + "SUBMIT")

        proc = iprecommit_run("--unstaged")
        expected_stdout = S(
            """\
            [iprecommit] NoForbiddenStrings: running
            example.txt
            [iprecommit] NoForbiddenStrings: failed


            [iprecommit] NewlineAtEndOfFile: running
            example.txt
            [iprecommit] NewlineAtEndOfFile: failed


            2 failed. Commit aborted.
            """
        )
        self.assertEqual(proc.stdout, expected_stdout)
        self.assertNotEqual(proc.returncode, 0)

    def test_failed_git_commit(self):
        self._create_repo()
        pre_commit_script = Path(".git/hooks/pre-commit").read_text()
        self.assertEqual(
            re.sub(r"version [0-9]\.[0-9]\.[0-9]", "version X.Y.Z", pre_commit_script),
            textwrap.dedent(
                """\
                #!/bin/sh

                # generated by iprecommit, version X.Y.Z

                set -e
                .venv/bin/iprecommit run
                """
            )
            % dict(tmpdir=self.tmpdir),
        )

        stage_do_not_submit_file()

        proc = run_shell(["git", "commit", "-m", "."], check=False, capture_stderr=True)
        expected_stderr = S(
            """\
            [iprecommit] NoForbiddenStrings: running
            includes_do_not_submit.txt
            [iprecommit] NoForbiddenStrings: failed


            [iprecommit] NewlineAtEndOfFile: running
            [iprecommit] NewlineAtEndOfFile: passed


            1 failed. Commit aborted.
            """
        )
        self.assertEqual(proc.stderr, expected_stderr)
        self.assertNotEqual(proc.returncode, 0)

    def test_run_fix(self):
        self.ensure_black_is_installed()

        precommit_text = S(
            """
            [[pre_commit]]
            cmd = ["black", "--check"]
            fix_cmd = ["black"]
            filters = ["*.py"]
            """
        )
        self._create_repo(precommit_text=precommit_text)

        p = Path("example.py")
        create_and_commit_file(p, "")
        p.write_text("x   = 5\n")

        run_shell(["git", "add", str(p)])
        proc = iprecommit_fix()
        expected_stdout = S(
            """\
            [iprecommit] black --check: fixing
            [iprecommit] black --check: finished


            """
        )
        self.assertEqual(proc.stdout, expected_stdout)
        self.assertEqual(proc.returncode, 0)

        self.assertEqual(p.read_text(), "x = 5\n")

    def test_glob_filters(self):
        self.ensure_black_is_installed()

        precommit_text = S(
            """
            [[pre_commit]]
            cmd = ["black", "--check"]
            filters = ["*.py"]
            """
        )
        self._create_repo(precommit_text=precommit_text)
        create_and_stage_file(
            "example.txt", "This does not parse as valid Python code.\n"
        )

        proc = iprecommit_run()
        expected_stdout = S(
            """\
            [iprecommit] black --check: skipped
            """
        )
        self.assertEqual(proc.stdout, expected_stdout)
        self.assertEqual(proc.returncode, 0)

    def test_uninstall(self):
        self._create_repo()
        self.assertTrue(Path(".git/hooks/pre-commit").exists())
        run_shell([".venv/bin/iprecommit", "uninstall"])
        self.assertFalse(Path(".git/hooks/pre-commit").exists())

    def test_python_format(self):
        self.ensure_black_is_installed()

        precommit_text = S(
            """
            [[pre_commit]]
            cmd = ["black", "--check"]
            pass_files = true
            filters = ["*.py"]
            """
        )
        self._create_repo(precommit_text=precommit_text)
        create_and_stage_file("bad_python_format.py", 'print(  "hello"  )\n')

        proc = iprecommit_run()
        expected_stdout = S(
            """\
            [iprecommit] black --check: running
            [iprecommit] black --check: failed


            1 failed. Commit aborted.
            """
        )
        self.assertEqual(proc.stdout, expected_stdout)
        self.assertEqual(proc.returncode, 1)

    def test_install_does_not_overwrite(self):
        self._create_repo(install_hook=False)

        Path(".git/hooks/pre-commit").write_text("...\n")

        proc = run_shell(
            [".venv/bin/iprecommit", "install"], check=False, capture_stderr=True
        )
        self.assertEqual(
            proc.stderr,
            "Error: .git/hooks/pre-commit already exists. Re-run with --force to overwrite.\n",
        )
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(Path("precommit.toml").exists())

        run_shell([".venv/bin/iprecommit", "install", "--force"])
        self.assertIn("iprecommit", Path(".git/hooks/pre-commit").read_text())
        self.assertTrue(Path("precommit.toml").exists())

    def test_uninstall_fails_if_hook_does_not_exist(self):
        self._create_repo(install_hook=False)

        proc = run_shell(
            [".venv/bin/iprecommit", "uninstall"], check=False, capture_stderr=True
        )
        self.assertEqual(proc.stderr, "Error: No pre-commit hook exists.\n")
        self.assertEqual(proc.returncode, 1)

    def test_uninstall_checks_for_iprecommit(self):
        self._create_repo(install_hook=False)

        hook_path = Path(".git/hooks/pre-commit")
        hook_path.write_text("...\n")

        proc = run_shell(
            [".venv/bin/iprecommit", "uninstall"], check=False, capture_stderr=True
        )
        self.assertEqual(
            proc.stderr,
            "Error: Existing pre-commit hook is not from iprecommit. Re-run with --force to uninstall anyway.\n",
        )
        self.assertEqual(proc.returncode, 1)

        self.assertTrue(hook_path.exists())

    def test_custom_hook_location(self):
        p = Path("custom_precommit.py")
        self._create_repo(path=p)
        self.assertTrue(p.exists())

        stage_do_not_submit_file()

        proc = run_shell(["git", "commit", "-m", "."], check=False, capture_stderr=True)
        expected_stderr = S(
            """\
            [iprecommit] NoForbiddenStrings: running
            includes_do_not_submit.txt
            [iprecommit] NoForbiddenStrings: failed


            [iprecommit] NewlineAtEndOfFile: running
            [iprecommit] NewlineAtEndOfFile: passed


            1 failed. Commit aborted.
            """
        )
        self.assertEqual(proc.stderr, expected_stderr)
        self.assertNotEqual(proc.returncode, 0)

    def test_commit_msg(self):
        precommit_text = S(
            """
            [[commit_msg]]
            cmd = ["iprecommit-commit-msg-format", "--require-capitalized"]
            """
        )
        self._create_repo(precommit_text=precommit_text)
        create_and_stage_file("example.txt", "Lorem ipsum\n")

        proc = run_shell(
            ["git", "commit", "-m", "lowercase"], check=False, capture_stderr=True
        )
        expected_stderr = S(
            """\
            [iprecommit] iprecommit-commit-msg-format --require-capitalized: running
            first line should be capitalized
            [iprecommit] iprecommit-commit-msg-format --require-capitalized: failed


            1 failed. Commit aborted.
            """
        )
        self.assertEqual(proc.stderr, expected_stderr)
        self.assertNotEqual(proc.returncode, 0)

    def test_pre_push(self):
        raise unittest.SkipTest(
            "iprecommit lost support after v0.3.1 for running pre-push checks on all changed files"
        )

        precommit_text = S(
            """
            from iprecommit import Pre, checks

            pre = Pre()
            pre.push.check(checks.NoDoNotCommit())
            pre.main()
            """
        )
        self._create_repo(precommit_text=precommit_text)
        create_and_commit_file("includes_do_not_submit.txt", "DO NOT " + "SUBMIT\n")

        with tempfile.TemporaryDirectory() as bare_repo_dir:
            os.chdir(bare_repo_dir)
            run_shell(["git", "init", "--bare"])
            os.chdir(self.tmpdir)
            run_shell(["git", "remote", "add", "origin", bare_repo_dir])

            proc = run_shell(
                ["git", "push", "-u", "origin", "master"],
                check=False,
                capture_stdout=True,
            )
            expected_stdout = S(
                """\
                [iprecommit] NoForbiddenStrings: running
                includes_do_not_submit.txt
                [iprecommit] NoForbiddenStrings: failed


                1 failed. Push aborted.
                """
            )
            self.assertEqual(proc.stdout, expected_stdout)
            self.assertNotEqual(proc.returncode, 0)

            # make sure nothing was pushed
            proc = run_shell(["git", "log", "origin/master"], check=False)
            self.assertNotEqual(proc.returncode, 0)

    def test_pre_push_commit_msg(self):
        precommit_text = S(
            """
            [[pre_push]]
            name = "NoForbiddenStrings"
            cmd = ["iprecommit-no-forbidden-strings", "--strings", "DO NOT PUSH", "--commits"]
            """
        )
        self._create_repo(precommit_text=precommit_text)
        commit_hash = create_and_commit_file(
            "example.txt", "lorem ipsum\n", message="DO NOT " + "PUSH"
        )

        with tempfile.TemporaryDirectory() as bare_repo_dir:
            os.chdir(bare_repo_dir)
            run_shell(["git", "init", "--bare"])
            os.chdir(self.tmpdir)
            run_shell(["git", "remote", "add", "origin", bare_repo_dir])

            proc = run_shell(
                ["git", "push", "-u", "origin", "master"],
                check=False,
                capture_stdout=True,
            )
            expected_stdout = S(
                f"""\
                [iprecommit] NoForbiddenStrings: running
                {commit_hash}
                [iprecommit] NoForbiddenStrings: failed


                1 failed. Push aborted.
                """
            )
            self.assertEqual(proc.stdout, expected_stdout)
            self.assertNotEqual(proc.returncode, 0)

            # make sure nothing was pushed
            proc = run_shell(["git", "log", "origin/master"], check=False)
            self.assertNotEqual(proc.returncode, 0)

    def test_non_ascii_filename(self):
        self._create_repo()
        create_and_stage_file("á.txt", "DO NOT " + "SUBMIT\n")

        proc = iprecommit_run()
        expected_stdout = S(
            """\
            [iprecommit] NoForbiddenStrings: running
            á.txt
            [iprecommit] NoForbiddenStrings: failed


            [iprecommit] NewlineAtEndOfFile: running
            [iprecommit] NewlineAtEndOfFile: passed


            1 failed. Commit aborted.
            """
        )
        self.assertEqual(proc.stdout, expected_stdout)
        self.assertNotEqual(proc.returncode, 0)

    def test_non_utf8_filename(self):
        if platform.system() != "Linux":
            raise unittest.SkipTest("This test only runs on Linux.")

        self._create_repo()

        p = b"\xc0\xaf.test"
        with open(p, "w") as f:
            f.write("DO NOT " + "SUBMIT\n")

        run_shell(["git", "add", p])

        proc = iprecommit_run()
        expected_stdout = S(
            f"""\
            [iprecommit] NoForbiddenStrings: running
            b'\\xc0\\xaf.test'
            [iprecommit] NoForbiddenStrings: failed


            [iprecommit] NewlineAtEndOfFile: running
            [iprecommit] NewlineAtEndOfFile: passed


            1 failed. Commit aborted.
            """
        )
        self.assertEqual(proc.stdout, expected_stdout)
        self.assertNotEqual(proc.returncode, 0)

    # TODO: pass_files=True, separately=True
    # TODO: filter checks by command-line argument to `run`
    # TODO: slow=True and --fast command-line argument
    # TODO: test nasty file names

    def ensure_black_is_installed(self):
        # TODO: install a fixed version of black as part of the test venv we set up
        self.assertIsNotNone(
            shutil.which("black"),
            msg="This test requires the `black` executable to be installed.",
        )


class TestUnit(unittest.TestCase):
    def test_filter_paths(self):
        paths = lambda *args: [Path(a) for a in args]

        self.assertEqual(
            lib._filter_paths(paths("a.py", "b.txt"), ["*.py"]), paths("a.py")
        )
        self.assertEqual(
            lib._filter_paths(paths("a.py", "b.txt"), ["*.txt"]), paths("b.txt")
        )

        self.assertEqual(
            lib._filter_paths(paths("a.py", "b.txt", "c.py"), ["*.py", "!c.py"]),
            paths("a.py"),
        )

        self.assertEqual(
            lib._filter_paths(
                paths("a.py", "b.txt", "c.py"), ["*.py", "!c.py", "b.txt"]
            ),
            paths("a.py", "b.txt"),
        )


S = textwrap.dedent


def iprecommit_run(*args, capture_stderr=False):
    return run_shell(
        [".venv/bin/iprecommit", "run"] + list(args),
        check=False,
        capture_stdout=True,
        capture_stderr=capture_stderr,
    )


def iprecommit_fix():
    return run_shell([".venv/bin/iprecommit", "fix"], capture_stdout=True)


def copy_and_stage_file(p):
    name = os.path.basename(p)
    shutil.copy(os.path.join(owndir, p), name)
    run_shell(["git", "add", name])


def create_and_stage_file(name, contents):
    p = Path(name)
    p.write_text(contents)
    run_shell(["git", "add", name])
    return p


def stage_do_not_submit_file():
    create_and_stage_file("includes_do_not_submit.txt", "DO NOT " + "SUBMIT\n")


# returns commit hash
def create_and_commit_file(name, contents, *, message="."):
    p = Path(name)
    p.write_text(contents)
    run_shell(["git", "add", str(p)])
    run_shell(["git", "commit", "-m", message])
    proc = run_shell(["git", "log", "-1", "--format=%H", "HEAD"], capture_stdout=True)
    return proc.stdout.strip()


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
