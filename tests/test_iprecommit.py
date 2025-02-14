import os
import platform
import re
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

from .common import Base, owndir, run_shell
from iprecommit import checks


class TestEndToEnd(Base):
    def test_failed_precommit_run(self):
        self._create_repo()
        stage_do_not_submit_file()

        proc = iprecommit_run()
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
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertNotEqual(0, proc.returncode)

    def test_no_files_staged(self):
        self._create_repo(clean=True)

        proc = iprecommit_run()
        expected_stdout = S(
            """\
            No files are staged in Git. Stage some files, or re-run with --unstaged or --all.
            """
        )
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertNotEqual(0, proc.returncode)

        proc = iprecommit_run("--unstaged")
        expected_stdout = S(
            """\
            No files are changed (staged or unstaged) in Git. Change some files, or re-run with --all.
            """
        )
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertNotEqual(0, proc.returncode)

    def test_only_check(self):
        self._create_repo()
        stage_do_not_submit_file()

        proc = iprecommit_run("--only", "NewlineAtEndOfFile")
        expected_stdout = S(
            """\
            [iprecommit] NoForbiddenStrings: skipped

            [iprecommit] NewlineAtEndOfFile: running
            [iprecommit] NewlineAtEndOfFile: passed
            """
        )
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertEqual(0, proc.returncode)

    def test_skip_check(self):
        self._create_repo()
        stage_do_not_submit_file()

        proc = iprecommit_run("--skip", "NoForbiddenStrings")
        expected_stdout = S(
            """\
            [iprecommit] NoForbiddenStrings: skipped

            [iprecommit] NewlineAtEndOfFile: running
            [iprecommit] NewlineAtEndOfFile: passed
            """
        )
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertEqual(0, proc.returncode)

    def test_skip_check_via_environment_variable(self):
        self._create_repo()
        stage_do_not_submit_file()

        os.environ["IPRECOMMIT_SKIP"] = "NoForbiddenStrings,NewlineAtEndOfFile"
        proc = iprecommit_run()
        del os.environ["IPRECOMMIT_SKIP"]
        expected_stdout = S(
            """\
            [iprecommit] NoForbiddenStrings: skipped

            [iprecommit] NewlineAtEndOfFile: skipped

            """
        )
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertEqual(0, proc.returncode)

    def test_fail_fast(self):
        self._create_repo(TOP_LEVEL_FAILFAST_PRECOMMIT)
        stage_do_not_submit_file()

        proc = iprecommit_run()
        expected_stdout = S(
            """\
            [iprecommit] NoForbiddenStrings: running
            includes_do_not_submit.txt
            [iprecommit] NoForbiddenStrings: failed

            [iprecommit] Failing fast: skipping 1 subsequent check.


            1 failed. Commit aborted.
            """
        )
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertNotEqual(0, proc.returncode)

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
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertNotEqual(0, proc.returncode)

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
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertNotEqual(0, proc.returncode)

    def test_failed_git_commit(self):
        self._create_repo()
        pre_commit_script = Path(".git/hooks/pre-commit").read_text()
        scrubbed = re.sub(
            r"version [0-9]\.[0-9]\.[0-9]", "version <scrubbed>", pre_commit_script
        )
        scrubbed = re.sub(r'export PATH="[^"]+"', 'export PATH="<scrubbed>"', scrubbed)
        self.maxDiff = None
        self.assertEqual(
            scrubbed,
            textwrap.dedent(
                """\
                #!/bin/sh

                # generated by iprecommit, version <scrubbed>

                set -e

                export PATH="<scrubbed>"

                if [ -x ".venv/bin/iprecommit" ]; then
                  ".venv/bin/iprecommit" run
                elif command -v iprecommit >/dev/null 2>&1; then
                  iprecommit run
                else
                  echo "ERROR: You have a pre-commit script at .git/hooks/pre-commit created by"
                  echo "iprecommit (https://github.com/iafisher/iprecommit), but the 'iprecommit'"
                  echo "executable could not be found."
                  echo
                  echo "To fix this:"
                  echo
                  echo "  pip install iprecommit"
                  echo "  iprecommit install --force"
                  echo
                  echo "Or you can delete .git/hooks/pre-commit if you don't want to use iprecommit."
                  exit 1
                fi
                """
            ),
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
        self.assertEqual(expected_stderr, proc.stderr)
        self.assertNotEqual(0, proc.returncode)

        self.assert_no_commits()

    def test_run_fix(self):
        self.ensure_black_is_installed()
        self._create_repo(precommit_text=PYTHON_FORMAT_PRECOMMIT)

        p = Path("example.py")
        create_and_commit_file(p, "")
        p.write_text("x   = 5\n")

        run_shell(["git", "add", str(p)])
        proc = iprecommit_fix()
        expected_stdout = S(
            """\
            [iprecommit] black --check: fixing
            reformatted example.py

            All done! ✨ 🍰 ✨
            1 file reformatted.
            [iprecommit] black --check: finished
            """
        )
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertEqual(0, proc.returncode)

        self.assertEqual(p.read_text(), "x = 5\n")

        # ensure iprecommit calls 'git add' on the file after fixing it
        proc = run_shell(["git", "diff", "--name-only"], capture_stdout=True)
        self.assertEqual("", proc.stdout)

    def test_glob_filters(self):
        self.ensure_black_is_installed()
        self._create_repo(precommit_text=PYTHON_FORMAT_PRECOMMIT)
        create_and_stage_file(
            "example.txt", "This does not parse as valid Python code.\n"
        )

        proc = iprecommit_run()
        expected_stdout = S(
            """\
            [iprecommit] black --check: skipped

            """
        )
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertEqual(0, proc.returncode)

    def test_uninstall(self):
        self._create_repo()
        self.assertTrue(Path(".git/hooks/pre-commit").exists())
        run_shell([".venv/bin/iprecommit", "uninstall"])
        self.assertFalse(Path(".git/hooks/pre-commit").exists())

    def test_python_format(self):
        self.ensure_black_is_installed()
        self._create_repo(precommit_text=PYTHON_FORMAT_PRECOMMIT)
        create_and_stage_file("bad_python_format.py", 'print(  "hello"  )\n')

        proc = iprecommit_run()
        expected_stdout = S(
            """\
            [iprecommit] black --check: running
            would reformat bad_python_format.py

            Oh no! 💥 💔 💥
            1 file would be reformatted.
            [iprecommit] black --check: failed


            1 failed. Commit aborted.
            """
        )
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertEqual(1, proc.returncode)

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
        self.assertEqual(1, proc.returncode)
        self.assertFalse(Path("precommit.toml").exists())

        run_shell([".venv/bin/iprecommit", "install", "--force"])
        self.assertIn("iprecommit", Path(".git/hooks/pre-commit").read_text())
        self.assertTrue(Path("precommit.toml").exists())

    def test_uninstall_fails_if_hook_does_not_exist(self):
        self._create_repo(install_hook=False)

        proc = run_shell(
            [".venv/bin/iprecommit", "uninstall"], check=False, capture_stderr=True
        )
        self.assertEqual("Error: No pre-commit hook exists.\n", proc.stderr)
        self.assertEqual(1, proc.returncode)

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
        self.assertEqual(1, proc.returncode)

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
        self.assertEqual(expected_stderr, proc.stderr)
        self.assertNotEqual(0, proc.returncode)

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


            [iprecommit] ***********************
            [iprecommit] checking commit message
            [iprecommit] ***********************


            [iprecommit] iprecommit-commit-msg-format --require-capitalized: running
            first line should be capitalized
            [iprecommit] iprecommit-commit-msg-format --require-capitalized: failed


            [iprecommit] commit message (also at .git/COMMIT_EDITMSG)
            lowercase
            [iprecommit] end commit message


            1 failed. Commit aborted.
            """
        )
        self.assertEqual(expected_stderr, proc.stderr)
        self.assertNotEqual(0, proc.returncode)

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
            self.assertEqual(expected_stdout, proc.stdout)
            self.assertNotEqual(0, proc.returncode)

            # make sure nothing was pushed
            proc = run_shell(["git", "log", "origin/master"], check=False)
            self.assertNotEqual(0, proc.returncode)

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

            # Git init might create default branch name as main or master
            # depending on computer settings
            proc = run_shell(
                ["git", "config", "init.defaultBranch"], check=True, capture_stdout=True
            )
            branch_name = proc.stdout.strip()

            proc = run_shell(
                ["git", "push", "-u", "origin", branch_name],
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
            self.assertEqual(expected_stdout, proc.stdout)
            self.assertNotEqual(0, proc.returncode)

            # make sure nothing was pushed
            proc = run_shell(["git", "log", "origin/master"], check=False)
            self.assertNotEqual(0, proc.returncode)

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
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertNotEqual(0, proc.returncode)

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
            """\
            [iprecommit] NoForbiddenStrings: running
            b'\\xc0\\xaf.test'
            [iprecommit] NoForbiddenStrings: failed

            [iprecommit] NewlineAtEndOfFile: running
            [iprecommit] NewlineAtEndOfFile: passed


            1 failed. Commit aborted.
            """
        )
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertNotEqual(0, proc.returncode)

    def test_run_precommit_on_all(self):
        self.ensure_black_is_installed()
        self._create_repo(precommit_text=PYTHON_FORMAT_PRECOMMIT)

        create_and_commit_file("bad_format1.py", "x   = 5\n", check=False)
        create_and_commit_file("bad_format2.py", "y   = 5\n", check=False)
        create_and_stage_file("bad_format3.py", "z   = 5\n")

        proc = iprecommit_run("--all")
        expected_stdout = S(
            """\
            [iprecommit] black --check: running
            would reformat bad_formatX.py
            would reformat bad_formatX.py
            would reformat bad_formatX.py

            Oh no! 💥 💔 💥
            3 files would be reformatted.
            [iprecommit] black --check: failed


            1 failed. Commit aborted.
            """
        )
        # black does not print out the file names in a deterministic order :(
        actual_stdout = re.sub(r"bad_format[0-9].py", "bad_formatX.py", proc.stdout)
        self.assertEqual(expected_stdout, actual_stdout)
        self.assertNotEqual(0, proc.returncode)

    def test_working_dir(self):
        precommit_text = S(
            """
            [[pre_commit]]
            name = "NoTypos"
            cmd = ["iprecommit-typos", "--paths", "has_a_typo.txt"]
            pass_files = false
            working_dir = "subdir/"
            """
        )
        self._create_repo(precommit_text=precommit_text)

        os.mkdir(os.path.join(self.tmpdir, "subdir"))
        # constructed like this so it doesn't trigger the check itself
        typo = "ab" + "bout"
        create_and_stage_file("subdir/has_a_typo.txt", f"{typo}\n")

        proc = iprecommit_run()
        expected_stdout = S(
            f"""\
            [iprecommit] NoTypos: running
            has_a_typo.txt
              typo on line 1: {typo} (did you mean 'about'?)
            [iprecommit] NoTypos: failed


            1 failed. Commit aborted.
            """
        )
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertNotEqual(0, proc.returncode)

    def test_autofix(self):
        self._create_repo(precommit_text=AUTOFIX_PRECOMMIT)

        create_and_stage_file("example.txt", "Lorem ipsum")

        self.assert_no_commits()
        proc = run_shell(["git", "commit", "-m", "."], check=False, capture_stderr=True)
        expected_stderr = S(
            f"""\
            [iprecommit] NoDoNotCommit: running
            [iprecommit] NoDoNotCommit: passed

            [iprecommit] NewlineAtEOF: running
            example.txt
            [iprecommit] NewlineAtEOF: failed


            [iprecommit] ******************
            [iprecommit] attempting autofix
            [iprecommit] ******************


            [iprecommit] NewlineAtEOF: fixing
            fixed: example.txt
            [iprecommit] NewlineAtEOF: finished


            [iprecommit] **********************
            [iprecommit] retrying after autofix
            [iprecommit] **********************


            [iprecommit] NoDoNotCommit: running
            [iprecommit] NoDoNotCommit: passed

            [iprecommit] NewlineAtEOF: running
            [iprecommit] NewlineAtEOF: passed
            """
        )
        self.assertEqual(expected_stderr, proc.stderr)
        self.assertEqual(0, proc.returncode)
        self.assert_one_commit()

        self.assertEqual("Lorem ipsum\n", Path("example.txt").read_text())

    def test_autofix_with_failfast(self):
        self._create_repo(precommit_text=FAILFAST_WITH_AUTOFIX_PRECOMMIT)

        create_and_stage_file("example.txt", "Lorem ipsum")

        self.assert_no_commits()
        proc = run_shell(["git", "commit", "-m", "."], check=False, capture_stderr=True)
        expected_stderr = S(
            f"""\
            [iprecommit] NewlineAtEOF: running
            example.txt
            [iprecommit] NewlineAtEOF: failed

            [iprecommit] Failing fast: skipping 1 subsequent check.


            [iprecommit] ******************
            [iprecommit] attempting autofix
            [iprecommit] ******************


            [iprecommit] NewlineAtEOF: fixing
            fixed: example.txt
            [iprecommit] NewlineAtEOF: finished


            [iprecommit] **********************
            [iprecommit] retrying after autofix
            [iprecommit] **********************


            [iprecommit] NewlineAtEOF: running
            [iprecommit] NewlineAtEOF: passed

            [iprecommit] NoDoNotCommit: running
            [iprecommit] NoDoNotCommit: passed
            """
        )
        self.assertEqual(expected_stderr, proc.stderr)
        self.assertEqual(0, proc.returncode)
        self.assert_one_commit()

        self.assertEqual("Lorem ipsum\n", Path("example.txt").read_text())

    def test_autofix_failed(self):
        self._create_repo(precommit_text=AUTOFIX_PRECOMMIT)

        create_and_stage_file("example.txt", "Lorem ipsum")
        stage_do_not_submit_file()

        self.assert_no_commits()
        proc = run_shell(["git", "commit", "-m", "."], check=False, capture_stderr=True)
        expected_stderr = S(
            f"""\
            [iprecommit] NoDoNotCommit: running
            includes_do_not_submit.txt
            [iprecommit] NoDoNotCommit: failed

            [iprecommit] NewlineAtEOF: running
            example.txt
            [iprecommit] NewlineAtEOF: failed


            [iprecommit] ******************
            [iprecommit] attempting autofix
            [iprecommit] ******************


            [iprecommit] NewlineAtEOF: fixing
            fixed: example.txt
            [iprecommit] NewlineAtEOF: finished


            [iprecommit] **********************
            [iprecommit] retrying after autofix
            [iprecommit] **********************


            [iprecommit] NoDoNotCommit: running
            includes_do_not_submit.txt
            [iprecommit] NoDoNotCommit: failed

            [iprecommit] NewlineAtEOF: running
            [iprecommit] NewlineAtEOF: passed


            1 failed. Commit aborted.
            """
        )
        self.assertEqual(expected_stderr, proc.stderr)
        self.assertNotEqual(0, proc.returncode)
        self.assert_no_commits()

        self.assertEqual("Lorem ipsum\n", Path("example.txt").read_text())

    def test_autofix_no_fix_possible(self):
        self._create_repo(precommit_text=AUTOFIX_PRECOMMIT)

        stage_do_not_submit_file()

        self.assert_no_commits()
        proc = run_shell(["git", "commit", "-m", "."], check=False, capture_stderr=True)
        expected_stderr = S(
            f"""\
            [iprecommit] NoDoNotCommit: running
            includes_do_not_submit.txt
            [iprecommit] NoDoNotCommit: failed

            [iprecommit] NewlineAtEOF: running
            [iprecommit] NewlineAtEOF: passed


            1 failed. Commit aborted.
            """
        )
        self.assertEqual(expected_stderr, proc.stderr)
        self.assertNotEqual(0, proc.returncode)
        self.assert_no_commits()

    def test_all_with_deleted_file(self):
        # REGRESSION TEST: `iprecommit run --all` should not pass names of deleted files to
        # commands.
        self._create_repo()

        create_and_commit_file("to_be_kept.txt", "Keep me!\n")
        create_and_commit_file("to_be_deleted.txt", "Delete me!\n")

        Path("unstaged.txt").write_text("DO NOT " + "COMMIT: I am unstaged!\n")
        # Regression test for bug where deleted files were erroneously passed on to commands.
        Path("to_be_deleted.txt").unlink()

        proc = iprecommit_run("--all")
        expected_stdout = S(
            """\
            [iprecommit] NoForbiddenStrings: running
            unstaged.txt
            [iprecommit] NoForbiddenStrings: failed

            [iprecommit] NewlineAtEndOfFile: running
            [iprecommit] NewlineAtEndOfFile: passed


            1 failed. Commit aborted.
            """
        )
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertNotEqual(0, proc.returncode)

    def test_exclude_filter(self):
        # REGRESSION TEST: An initial exclude filter should not exclude everything.
        precommit_text = S(
            """
            [[pre_commit]]
            name = "NoForbiddenStrings"
            cmd = ["iprecommit-no-forbidden-strings", "--paths"]
            filters = ["!dict.txt"]
            """
        )
        self._create_repo(precommit_text=precommit_text)

        create_and_stage_file("example.txt", "Lorem ipsum\n")
        create_and_stage_file("dict.txt", "DO NOT" + " COMMIT\n")

        proc = iprecommit_run()
        expected_stdout = S(
            """\
            [iprecommit] NoForbiddenStrings: running
            [iprecommit] NoForbiddenStrings: passed
            """
        )
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertEqual(0, proc.returncode)

    def test_new_untracked_file_with_fixes(self):
        # REGRESSION TEST: iprecommit should ignore untracked files even if they have problems.
        self._create_repo(precommit_text=PYTHON_FORMAT_PRECOMMIT)

        create_and_stage_file("example.txt", "Lorem ipsum\n")
        Path("bad_python_format.py").write_text("x   = 5\n")

        proc = iprecommit_run()
        expected_stdout = S(
            """\
            [iprecommit] black --check: skipped

            """
        )
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertEqual(0, proc.returncode)

    def test_new_untracked_file_and_unstaged_flag(self):
        self._create_repo(precommit_text=PYTHON_FORMAT_PRECOMMIT)

        create_and_stage_file("example.txt", "Lorem ipsum\n")
        Path("bad_python_format.py").write_text("x   = 5\n")

        proc = iprecommit_run("--unstaged")
        expected_stdout = S(
            """\
            [iprecommit] black --check: running
            would reformat bad_python_format.py

            Oh no! 💥 💔 💥
            1 file would be reformatted.
            [iprecommit] black --check: failed


            1 failed. Commit aborted.
            """
        )
        self.assertEqual(expected_stdout, proc.stdout)
        self.assertEqual(1, proc.returncode)

    def test_help_text(self):
        self.maxDiff = None

        proc = run_shell([".venv/bin/iprecommit", "--help"], capture_stdout=True)
        expected_stdout = S(
            """\
            usage: iprecommit [-h] [--version]  ...

            Dead-simple Git pre-commit hook management.

            options:
              -h, --help      show this help message and exit
              --version       show program's version number and exit

            subcommands:

                install       Install an iprecommit hook in the current Git repository.
                uninstall     Uninstall the iprecommit hook in the current Git repository.
                run           Manually run the pre-commit hook.
                fix           Apply fixes to failing checks.
                run-commit-msg
                              Manually run the commit-msg hook.
                run-pre-push  Manually run the pre-push hook.
            """
        )
        self.assertEqual(expected_stdout, S(proc.stdout))

        proc = run_shell(
            [".venv/bin/iprecommit", "install", "--help"], capture_stdout=True
        )
        expected_stdout = S(
            """\
            usage: iprecommit install [-h] [--force] [--path PATH]

            Install an iprecommit hook in the current Git repository.

            options:
              -h, --help   show this help message and exit
              --force      Overwrite existing pre-commit hook.
              --path PATH  Customize configuration file path. [default: precommit.toml]
            """
        )
        self.assertEqual(expected_stdout, S(proc.stdout))

        proc = run_shell(
            [".venv/bin/iprecommit", "uninstall", "--help"], capture_stdout=True
        )
        expected_stdout = S(
            """\
            usage: iprecommit uninstall [-h] [--force]

            Uninstall the iprecommit hook in the current Git repository.

            options:
              -h, --help  show this help message and exit
              --force     Uninstall a non-iprecommit hook.
            """
        )
        self.assertEqual(expected_stdout, S(proc.stdout))

        proc = run_shell([".venv/bin/iprecommit", "run", "--help"], capture_stdout=True)
        expected_stdout = S(
            """\
            usage: iprecommit run [-h] [--config CONFIG] [--unstaged | --all]
                                  [--fail-fast] [--skip CHECK] [--only CHECK]

            Manually run the pre-commit hook.

            options:
              -h, --help       show this help message and exit
              --config CONFIG  Custom path to TOML configuration file. [default:
                               precommit.toml]
              --unstaged       Also run on unstaged files.
              --all            Run on all files in the repository.
              --fail-fast      Stop at the first failing check.
              --skip CHECK     Skip the given check (repeatable).
              --only CHECK     Run only the given check (repeatable).
            """
        )
        self.assertEqual(expected_stdout, S(proc.stdout))

        proc = run_shell([".venv/bin/iprecommit", "fix", "--help"], capture_stdout=True)
        expected_stdout = S(
            """\
            usage: iprecommit fix [-h] [--config CONFIG] [--unstaged | --all]
                                  [--skip CHECK] [--only CHECK]

            Apply fixes to failing checks.

            options:
              -h, --help       show this help message and exit
              --config CONFIG  Custom path to TOML configuration file. [default:
                               precommit.toml]
              --unstaged       Also run on unstaged files.
              --all            Run on all files in the repository.
              --skip CHECK     Skip the given check (repeatable).
              --only CHECK     Run only the given check (repeatable).
            """
        )
        self.assertEqual(expected_stdout, S(proc.stdout))

        proc = run_shell(
            [".venv/bin/iprecommit", "run-commit-msg", "--help"], capture_stdout=True
        )
        expected_stdout = S(
            """\
            usage: iprecommit run-commit-msg [-h] [--commit-msg COMMIT_MSG]
                                             [--config CONFIG]

            Manually run the commit-msg hook.

            options:
              -h, --help            show this help message and exit
              --commit-msg COMMIT_MSG
                                    Path to commit message file.
              --config CONFIG       Custom path to TOML configuration file. [default:
                                    precommit.toml]
            """
        )
        self.assertEqual(expected_stdout, S(proc.stdout))

        proc = run_shell(
            [".venv/bin/iprecommit", "run-pre-push", "--help"], capture_stdout=True
        )
        expected_stdout = S(
            """\
            usage: iprecommit run-pre-push [-h] [--remote REMOTE] [--config CONFIG]

            Manually run the pre-push hook.

            options:
              -h, --help       show this help message and exit
              --remote REMOTE
              --config CONFIG  Custom path to TOML configuration file. [default:
                               precommit.toml]
            """
        )
        self.assertEqual(expected_stdout, S(proc.stdout))

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

    def assert_no_commits(self):
        proc = run_shell(["git", "log", "--oneline"], check=False, capture_stdout=True)
        self.assertEqual("", proc.stdout)

    def assert_one_commit(self):
        proc = run_shell(["git", "log", "--oneline"], check=True, capture_stdout=True)
        self.assertEqual(1, len(proc.stdout.splitlines()))


class TestUnit(unittest.TestCase):
    def test_filter_paths(self):
        paths = lambda *args: [Path(a) for a in args]

        self.assertEqual(
            paths("a.py"), checks.filter_paths(paths("a.py", "b.txt"), ["*.py"])
        )
        self.assertEqual(
            paths("b.txt"), checks.filter_paths(paths("a.py", "b.txt"), ["*.txt"])
        )

        self.assertEqual(
            paths("a.py"),
            checks.filter_paths(paths("a.py", "b.txt", "c.py"), ["*.py", "!c.py"]),
        )

        self.assertEqual(
            paths("a.py", "b.txt"),
            checks.filter_paths(
                paths("a.py", "b.txt", "c.py"), ["*.py", "!c.py", "b.txt"]
            ),
        )

        self.assertEqual(
            paths("a.txt"), checks.filter_paths(paths("a.txt", "b.txt"), ["!b.txt"])
        )


S = textwrap.dedent


PYTHON_FORMAT_PRECOMMIT = """
[[pre_commit]]
cmd = ["black", "--check"]
fix_cmd = ["black"]
filters = ["*.py"]
"""

AUTOFIX_PRECOMMIT = """
autofix = true

[[pre_commit]]
name = "NoDoNotCommit"
cmd = ["iprecommit-no-forbidden-strings", "--paths"]

[[pre_commit]]
name = "NewlineAtEOF"
cmd = ["iprecommit-newline-at-eof"]
fix_cmd = ["iprecommit-newline-at-eof", "--fix"]
"""

TOP_LEVEL_FAILFAST_PRECOMMIT = """\
fail_fast = true

[[pre_commit]]
name = "NoForbiddenStrings"
cmd = ["iprecommit-no-forbidden-strings", "--paths"]

[[pre_commit]]
name = "NewlineAtEOF"
cmd = ["iprecommit-newline-at-eof"]
fix_cmd = ["iprecommit-newline-at-eof", "--fix"]
"""

FAILFAST_WITH_AUTOFIX_PRECOMMIT = """\
fail_fast = false

[[pre_commit]]
name = "NewlineAtEOF"
cmd = ["iprecommit-newline-at-eof"]
fix_cmd = ["iprecommit-newline-at-eof", "--fix"]
autofix = true
fail_fast = true

[[pre_commit]]
name = "NoDoNotCommit"
cmd = ["iprecommit-no-forbidden-strings", "--paths"]
"""


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
def create_and_commit_file(name, contents, *, message=".", check=True):
    p = Path(name)
    p.write_text(contents)
    run_shell(["git", "add", str(p)])
    run_shell(["git", "commit", "-m", message] + ([] if check else ["-n"]))
    proc = run_shell(["git", "log", "-1", "--format=%H", "HEAD"], capture_stdout=True)
    return proc.stdout.strip()


if __name__ == "__main__":
    unittest.main()
