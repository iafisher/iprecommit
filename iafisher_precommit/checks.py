import sys
from .lib import Precommit, Problem, run


class NoStagedAndUnstagedChanges:
    """Checks that the file doesn't also have unstaged changes."""

    def check(self, repo_info, path):
        if path in repo_info.unstaged_files:
            return Problem("file has both staged and unstaged changes")


class NoWhitespaceInFilePath:
    """Checks that the file path contains no whitespace."""

    def check(self, repo_info, path):
        if any(c.isspace() for c in path):
            return Problem("file path contains whitespace")


class PythonFormat:
    """Checks the format of Python files using black."""

    pattern = Precommit.pattern_from_file_ext("py")

    def check(self, repo_info, path):
        black = run(["black", "--check", path])
        if black.returncode != 0:
            return Problem("bad formatting", autofix=["black", path])


class PythonStyle:
    """Lints Python files using flake8."""

    pattern = Precommit.pattern_from_file_ext("py")

    def check(self, repo_info, path):
        flake8 = run(["flake8", path])
        if flake8.returncode != 0:
            errors = flake8.stdout.decode(sys.getdefaultencoding())
            return Problem("lint error(s)", verbose_message=errors)


class CheckWithCommand:
    """Checks that invoking `cmd` on the file path results in an exit code of 0."""

    def __init__(self, cmd):
        if isinstance(cmd, list):
            self.cmdname = cmd[0]
            self.cmd = cmd
        else:
            self.cmdname = cmd
            self.cmd = [self.cmdname]

    def check(self, repo_info, path):
        result = run(self.cmd + [path])
        if result.returncode != 0:
            return Problem(f"command {self.cmdname!r} failed")
