import sys
from .lib import FileCheck, Precommit, Problem, RepoCheck, pathfilter, run


class NoStagedAndUnstagedChanges(RepoCheck):
    """Checks that the file doesn't also have unstaged changes."""

    fixable = True

    def check(self, repository):
        both = set(repository.staged_files).intersection(set(repository.unstaged_files))
        if both:
            message = "\n".join(sorted(both))
            return Problem(
                "unstaged changes to a staged file",
                verbose_message=message,
                autofix=["git", "add"] + list(both),
            )


class NoWhitespaceInFilePath(FileCheck):
    """Checks that the file path contains no whitespace."""

    def check(self, path):
        if any(c.isspace() for c in path):
            return Problem("file path contains whitespace")


class PythonFormat(RepoCheck):
    """Checks the format of Python files using black."""

    fixable = True

    def check(self, repository):
        python = pathfilter(repository.staged_files, Precommit.pattern_from_ext("py"))
        if not python:
            return
        black = run(["black", "--check"] + python)
        if black.returncode != 0:
            errors = black.stdout.decode(sys.getdefaultencoding()).strip()
            return Problem(
                "bad formatting",
                verbose_message=errors,
                autofix=["black"] + repository.staged_files,
            )


class PythonStyle(RepoCheck):
    """Lints Python files using flake8."""

    def __init__(self, *, args=None):
        self.args = args if args is not None else []

    def check(self, repository):
        python = pathfilter(repository.staged_files, Precommit.pattern_from_ext("py"))
        if not python:
            return
        flake8 = run(["flake8"] + self.args + python)
        if flake8.returncode != 0:
            errors = flake8.stdout.decode(sys.getdefaultencoding()).strip()
            return Problem("lint error(s)", verbose_message=errors)


class RepoCommand(RepoCheck):
    """Checks that `cmd` returns an exit code of 0."""

    def __init__(self, cmd):
        if isinstance(cmd, list):
            self.cmdname = cmd[0]
            self.cmd = cmd
        else:
            self.cmdname = cmd
            self.cmd = [self.cmdname]

    def check(self, repository):
        result = run(self.cmd)

        if result.returncode != 0:
            output = result.stdout.decode(sys.getdefaultencoding()).strip()
            return Problem(f"command {self.cmdname!r} failed", verbose_message=output)

    def name(self):
        return f"RepoCommand({' '.join(self.cmd)!r})"

    def help(self):
        return f"Checks that {' '.join(self.cmd)!r} returns an exit code of 0."


class FileCommand(FileCheck):
    """Checks that invoking `cmd` on the file path results in an exit code of 0."""

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
            output = result.stdout.decode(sys.getdefaultencoding()).strip()
            return Problem(f"command {self.cmdname!r} failed", verbose_message=output)
