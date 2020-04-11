import sys
from .lib import FileCheck, Problem, RepoCheck, pattern_from_ext, run


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


# We construct it like this so the string literal doesn't trigger the check itself.
DO_NOT_SUBMIT = "DO NOT " + "SUBMIT"


class DoNotSubmit(FileCheck):
    f"""Checks that the file does not contain the string '{DO_NOT_SUBMIT}'."""

    def check(self, path):
        with open(path, "r") as f:
            if DO_NOT_SUBMIT in f.read().upper():
                return Problem(f"file contains '{DO_NOT_SUBMIT}'")


class NoWhitespaceInFilePath(FileCheck):
    """Checks that the file path contains no whitespace."""

    def check(self, path):
        if any(c.isspace() for c in path):
            return Problem("file path contains whitespace")


def Command(*args, per_file=False, **kwargs):
    if per_file:
        return FileCommand(*args, **kwargs)
    else:
        return RepoCommand(*args, **kwargs)


class RepoCommand(RepoCheck):
    """Checks that the command returns an exit code of 0."""

    def __init__(self, cmd, *, args=None, pass_files=False):
        self.pass_files = pass_files
        if isinstance(cmd, list):
            self.cmd = cmd[0]
            self.args = cmd[1:] + (args if args is not None else [])
        else:
            self.cmd = cmd
            self.args = args if args is not None else []

    def check(self, repository):
        if self.pass_files:
            cmdline = [self.cmd] + self.args + repository.filtered
        else:
            cmdline = [self.cmd] + self.args

        result = run(cmdline)
        if result.returncode != 0:
            output = result.stdout.decode(sys.getdefaultencoding()).strip()
            return Problem(
                self.get_failure_message(),
                verbose_message=output,
                autofix=self.get_autofix(repository),
            )

    def name(self):
        if type(self) is RepoCommand:
            return f"RepoCommand({self.cmd!r})"
        else:
            return super().name()

    def get_failure_message(self):
        return f"command {self.cmd!r} failed"

    def get_autofix(self, repository):
        return None


class FileCommand(FileCheck):
    """Checks that invoking `cmd` on the file path results in an exit code of 0."""

    def __init__(self, cmd):
        if isinstance(cmd, list):
            self.cmd = cmd[0]
            self.args = cmd[1:]
        else:
            self.cmd = cmd
            self.args = []

    def check(self, path):
        result = run([self.cmd] + self.args + [path])

        if result.returncode != 0:
            output = result.stdout.decode(sys.getdefaultencoding()).strip()
            return Problem(f"command {self.cmd!r} failed", verbose_message=output)


class PythonFormat(RepoCommand):
    """Checks the format of Python files using black."""

    fixable = True
    pattern = pattern_from_ext("py")

    def __init__(self, **kwargs):
        super().__init__(["black", "--check"], pass_files=True, **kwargs)

    def get_failure_message(self):
        return "bad formatting"

    def get_autofix(self, repository):
        return ["black"] + repository.filtered


class PythonStyle(RepoCommand):
    """Lints Python files using flake8."""

    pattern = pattern_from_ext("py")

    def __init__(self, *, args=None, **kwargs):
        args = args or []
        if not any(a.startswith("--max-line-length") for a in args):
            args = (args or []) + ["--max-line-length=88"]
        super().__init__("flake8", pass_files=True, args=args, **kwargs)

    def get_failure_message(self):
        return "Python lint error(s)"


class JavaScriptStyle(RepoCommand):
    """Lints JavaScript files using ESLint."""

    fixable = True
    pattern = pattern_from_ext("js")

    def __init__(self, **kwargs):
        super().__init__(["npx", "eslint"], **kwargs)

    def get_failure_message(self):
        return "JavaScript lint error(s)"

    def get_autofix(self, repository):
        return ["npx", "eslint", "--fix"] + repository.filtered
