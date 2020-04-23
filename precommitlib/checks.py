import sys
from .lib import BaseCheck, Problem, UsageError


class NoStagedAndUnstagedChanges(BaseCheck):
    """Checks that each staged file doesn't also have unstaged changes."""

    def check(self, fs, repository):
        both = set(repository.staged).intersection(set(repository.unstaged))
        if both:
            message = "\n".join(sorted(both))
            return Problem(message=message, autofix=["git", "add"] + list(both))

    def is_fixable(self):
        return True


# We construct it like this so the string literal doesn't trigger the check itself.
DO_NOT_SUBMIT = "DO NOT " + "SUBMIT"


class DoNotSubmit(BaseCheck):
    f"""Checks that files do not contain the string '{DO_NOT_SUBMIT}'."""

    def check(self, fs, repository):
        bad_paths = []
        for path in self.filter(repository.staged):
            with fs.open(path, "rb") as f:
                if DO_NOT_SUBMIT.encode("ascii") in f.read().upper():
                    bad_paths.append(path)

        if bad_paths:
            message = "\n".join(sorted(bad_paths))
            return Problem(f"file contains '{DO_NOT_SUBMIT}'", message=message)


class NoWhitespaceInFilePath(BaseCheck):
    """Checks that file paths do not contain whitespace."""

    def check(self, fs, repository):
        bad_paths = []
        for path in self.filter(repository.staged):
            if any(c.isspace() for c in path):
                bad_paths.append(path)

        if bad_paths:
            message = "\n".join(sorted(bad_paths))
            return Problem("file path contains whitespace", message=message)


class Command(BaseCheck):
    def __init__(
        self, name, cmd, fix=None, pass_files=False, separately=False, **kwargs
    ):
        super().__init__(**kwargs)
        self.name = name
        self.cmd = cmd
        self.fix = fix

        if separately is True and pass_files is False:
            raise UsageError("if `separately` is True, `pass_files` must also be True")

        self.pass_files = pass_files
        self.separately = separately

    def check(self, fs, repository):
        if self.separately:
            message_builder = []
            problem = False
            for path in self.filter(repository.staged):
                result = fs.run(self.cmd + [path])
                if result.returncode != 0:
                    problem = True
                output = result.stdout.decode(sys.getdefaultencoding()).strip()
                message_builder.append(output)

            if problem:
                message = "\n\n".join(message_builder)
                return Problem(message=message, autofix=self.fix)
        else:
            args = self.filter(repository.staged) if self.pass_files else []
            cmd = self.cmd + args
            result = fs.run(cmd)
            if result.returncode != 0:
                output = result.stdout.decode(sys.getdefaultencoding()).strip()
                autofix = self.fix + args if self.fix else None
                return Problem(message=output, autofix=autofix)

    def get_name(self):
        return self.name

    def is_fixable(self):
        return self.fix is not None


def PythonFormat(**kwargs):
    return Command(
        "PythonFormat",
        ["black", "--check"],
        pass_files=True,
        pattern=r".*\.py",
        fix=["black"],
        **kwargs,
    )


def PythonStyle(**kwargs):
    return Command(
        "PythonStyle",
        ["flake8", "--max-line-length=88"],
        pass_files=True,
        pattern=r".*\.py",
        **kwargs,
    )


def JavaScriptStyle(**kwargs):
    return Command(
        "JavaScriptStyle",
        ["npx", "eslint"],
        pass_files=True,
        pattern=r".*\.js",
        fix=["npx", "eslint", "--fix"],
        **kwargs,
    )
