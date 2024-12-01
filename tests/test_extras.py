import contextlib
import io
import os
import unittest
from pathlib import Path

from .common import Base, run_shell
from iprecommit.extras import commit_msg_format


class TestNewlineAtEOF(Base):
    def test_check(self):
        os.chdir(self.tmpdir)

        p = Path("example.txt")
        p.write_text("no newline")

        proc = run_shell(
            ["iprecommit-newline-at-eof", p], check=False, capture_stdout=True
        )
        self.assertEqual("example.txt\n", proc.stdout)
        self.assertNotEqual(0, proc.returncode)

        p = Path("example2.txt")
        p.write_text("with a newline\n")

        proc = run_shell(["iprecommit-newline-at-eof", p], capture_stdout=True)
        self.assertEqual("", proc.stdout)

    def test_check_disallow_empty(self):
        os.chdir(self.tmpdir)

        p = Path("empty.txt")
        p.write_text("")

        proc = run_shell(["iprecommit-newline-at-eof", p], capture_stdout=True)
        self.assertEqual("", proc.stdout)

        proc = run_shell(
            ["iprecommit-newline-at-eof", "--disallow-empty", p],
            check=False,
            capture_stdout=True,
        )
        self.assertEqual("empty.txt\n", proc.stdout)
        self.assertNotEqual(0, proc.returncode)

    def test_fix(self):
        os.chdir(self.tmpdir)

        p = Path("example.txt")
        p.write_text("no newline")

        proc = run_shell(["iprecommit-newline-at-eof", "--fix", p], capture_stdout=True)
        self.assertEqual("fixed: example.txt\n", proc.stdout)

        self.assertEqual("no newline\n", p.read_text())


class TestCommitMsgFormat(unittest.TestCase):
    def test_empty_commit(self):
        self.assertFalse(
            commit_msg_format.check(
                "",
                max_first_line_length=None,
                max_line_length=None,
                require_capitalized=False,
            )
        )
        self.assertFalse(
            commit_msg_format.check(
                "\n\n",
                max_first_line_length=None,
                max_line_length=None,
                require_capitalized=False,
            )
        )
        self.assertFalse(
            commit_msg_format.check(
                "\n\n\n# Comment only\n",
                max_first_line_length=None,
                max_line_length=None,
                require_capitalized=False,
            )
        )

    def test_first_line_leading_whitespace(self):
        self.assertFalse(
            commit_msg_format.check(
                "   leading whitespace\n",
                max_first_line_length=None,
                max_line_length=None,
                require_capitalized=False,
            )
        )

    def test_line_too_long(self):
        self.assertFalse(
            commit_msg_format.check(
                "123456\n",
                max_first_line_length=5,
                max_line_length=None,
                require_capitalized=False,
            )
        )

        self.assertFalse(
            commit_msg_format.check(
                "first_line\n\n123\n123456",
                max_first_line_length=None,
                max_line_length=5,
                require_capitalized=False,
            )
        )

    def test_require_capitalized(self):
        self.assertFalse(
            commit_msg_format.check(
                "should be capitalized\n",
                max_first_line_length=None,
                max_line_length=None,
                require_capitalized=True,
            )
        )

    def test_blank_line_after_first_line(self):
        self.assertFalse(
            commit_msg_format.check(
                "first line\nno blank line",
                max_first_line_length=None,
                max_line_length=None,
                require_capitalized=False,
            )
        )

    def test_ignore_comments(self):
        self.assertTrue(
            commit_msg_format.check(
                "first line\n\n# This line would be too long, but it's a comment.\n",
                max_first_line_length=None,
                max_line_length=10,
                require_capitalized=False,
            )
        )

        self.assertTrue(
            commit_msg_format.check(
                "first line\n\n  # This comment begins with leading whitespace.\n",
                max_first_line_length=None,
                max_line_length=10,
                require_capitalized=False,
            )
        )

    def test_ok_commit(self):
        self.assertTrue(
            commit_msg_format.check(
                "This is an example of a good commit.\n\nNo line is too long, and there is a blank line after the first line.",
                max_first_line_length=72,
                max_line_length=100,
                require_capitalized=False,
            )
        )

    def test_ignore_diff_lines(self):
        first_line_length = len(REAL_COMMIT_MSG.splitlines()[0])
        # Some of the lines of the diff are longer than the max, but they should be ignored.
        self.assertTrue(
            commit_msg_format.check(
                REAL_COMMIT_MSG,
                max_first_line_length=None,
                max_line_length=first_line_length,
                require_capitalized=False,
            )
        )

    def test_line_numbers(self):
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            self.assertFalse(
                commit_msg_format.check(
                    "line 1\n\n# line 3\nline 4 is too long",
                    max_first_line_length=None,
                    max_line_length=10,
                    require_capitalized=False,
                )
            )

        # should correctly print line 4 even though line 3 was a comment and skipped
        self.assertEqual(
            "line 4 too long: len=18, max=10: line 4 is...\n", f.getvalue()
        )


REAL_COMMIT_MSG = """\
add --fix flag to iprecommit-newline-at-eof

# Please enter the commit message for your changes. Lines starting
# with '#' will be ignored, and an empty message aborts the commit.
#
# Date:      Sun Dec 1 09:13:25 2024 -0500
#
# On branch master
# Your branch is ahead of 'origin/master' by 2 commits.
#   (use "git push" to publish your local commits)
#
# Changes to be committed:
#	modified:   iprecommit/main.py
#
# ------------------------ >8 ------------------------
# Do not modify or remove the line above.
# Everything below it will be ignored.
diff --git a/iprecommit/main.py b/iprecommit/main.py
index 11fc86c..5d69a0e 100644
--- a/iprecommit/main.py
+++ b/iprecommit/main.py
@@ -229,6 +229,7 @@ cmd = ["iprecommit-no-forbidden-strings", "--paths"]
 [[pre_commit]]
 name = "NewlineAtEndOfFile"
 cmd = ["iprecommit-newline-at-eof"]
+fix_cmd = ["iprecommit-newline-at-eof", "--fix"]
 
 # [[pre_commit]]
 # name = "PythonFormat"
"""
