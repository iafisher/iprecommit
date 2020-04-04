import sys
from .lib import Precommit, Problem, run


class NoStagedAndUnstagedChanges:
    """Checks that the file doesn't also have unstaged changes."""

    def check(self, repo_info):
        both = set(repo_info.staged_files).intersection(set(repo_info.unstaged_files))
        if both:
            message = "\n".join(sorted(both))
            return Problem(
                "unstaged changes to a staged file",
                verbose_message=message,
                autofix=["git", "add"] + list(both),
            )


class NoWhitespaceInFilePath:
    """Checks that the file path contains no whitespace."""

    per_file = True

    def check(self, path):
        if any(c.isspace() for c in path):
            return Problem("file path contains whitespace")


class PythonFormat:
    """Checks the format of Python files using black."""

    pattern = Precommit.pattern_from_file_ext("py")

    def check(self, repo_info):
        black = run(["black", "--check"] + repo_info.staged_files)
        if black.returncode != 0:
            errors = black.stdout.decode(sys.getdefaultencoding()).strip()
            return Problem(
                "bad formatting",
                verbose_message=errors,
                autofix=["black"] + repo_info.staged_files,
            )


class PythonStyle:
    """Lints Python files using flake8."""

    pattern = Precommit.pattern_from_file_ext("py")

    def __init__(self, *, args=None):
        self.args = args if args is not None else []

    def check(self, repo_info):
        flake8 = run(["flake8"] + self.args + repo_info.staged_files)
        if flake8.returncode != 0:
            errors = flake8.stdout.decode(sys.getdefaultencoding()).strip()
            return Problem("lint error(s)", verbose_message=errors)


class CheckWithCommand:
    """Checks that invoking `cmd` on the file path results in an exit code of 0."""

    per_file = True

    def __init__(self, cmd):
        if isinstance(cmd, list):
            self.cmdname = cmd[0]
            self.cmd = cmd
        else:
            self.cmdname = cmd
            self.cmd = [self.cmdname]

    def check(self, path):
        result = run(self.cmd + [path])
        if result.returncode != 0:
            return Problem(f"command {self.cmdname!r} failed")
