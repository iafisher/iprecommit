"""
A suite of useful pre-commit checks.

Author:  Ian Fisher (iafisher@fastmail.com)
Version: May 2020
"""
import textwrap
from typing import List, Optional

from . import utils
from .lib import BaseCheck, Problem, Repository, UsageError, run


def stream(msg: str) -> None:
    """
    Prints the message.

    This is the function that all checks should use to emit output, like this:

        if stream_output:
            stream(msg)

    """
    print(textwrap.indent(msg, utils.blue("|  ")))


class NoStagedAndUnstagedChanges(BaseCheck):
    """Checks that each staged file doesn't also have unstaged changes."""

    def check(
        self, repository: Repository, *, stream_output: bool
    ) -> Optional[Problem]:
        both = set(repository.staged).intersection(set(repository.unstaged))
        if both:
            message = "\n".join(sorted(both))
            if stream_output:
                stream(message)
            return Problem(autofix=["git", "add"] + list(both))

        return None

    def is_fixable(self) -> bool:
        return True


# We construct it like this so the string literal doesn't trigger the check itself.
DO_NOT_SUBMIT = "DO NOT " + "SUBMIT"


class DoNotSubmit(BaseCheck):
    f"""Checks that files do not contain the string '{DO_NOT_SUBMIT}'."""

    def check(
        self, repository: Repository, *, stream_output: bool
    ) -> Optional[Problem]:
        bad_paths = []
        for path in self.filter(repository.staged):
            with open(path, "rb") as f:
                if DO_NOT_SUBMIT.encode("ascii") in f.read().upper():
                    bad_paths.append(path)

        if bad_paths:
            message = "\n".join(sorted(bad_paths))
            if stream_output:
                stream(message)
            return Problem(message=f"file contains '{DO_NOT_SUBMIT}'")

        return None


class NoWhitespaceInFilePath(BaseCheck):
    """Checks that file paths do not contain whitespace."""

    def check(
        self, repository: Repository, *, stream_output: bool
    ) -> Optional[Problem]:
        bad_paths = []
        for path in self.filter(repository.staged):
            if any(c.isspace() for c in path):
                bad_paths.append(path)

        if bad_paths:
            message = "\n".join(sorted(bad_paths))
            if stream_output:
                stream(message)
            return Problem(message="file path contains whitespace")

        return None


class Command(BaseCheck):
    def __init__(
        self,
        name: str,
        cmd: List[str],
        fix: Optional[List[str]] = None,
        pass_files: bool = False,
        separately: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.name = name
        self.cmd = cmd
        self.fix = fix

        if separately is True and pass_files is False:
            raise UsageError("if `separately` is True, `pass_files` must also be True")

        self.pass_files = pass_files
        self.separately = separately

    def check(
        self, repository: Repository, *, stream_output: bool
    ) -> Optional[Problem]:
        if self.separately:
            problem = False
            for path in self.filter(repository.staged):
                r = run(self.cmd + [path], stream_output=stream_output)
                if r.returncode != 0:
                    problem = True

            if problem:
                # TODO(2020-04-23): There should be a separate fix command for each
                # file path.
                return Problem(autofix=self.fix)
        else:
            args = self.filter(repository.staged) if self.pass_files else []
            cmd = self.cmd + args
            r = run(cmd, stream_output=stream_output)
            if r.returncode != 0:
                autofix = self.fix + args if self.fix else None
                return Problem(autofix=autofix)

        return None

    def get_name(self) -> str:
        return self.name

    def is_fixable(self) -> bool:
        return self.fix is not None


def PythonFormat(
    args: List[str] = [], *, include: List[str] = [], **kwargs
) -> BaseCheck:
    return Command(
        "PythonFormat",
        ["black", "--check"] + args,
        pass_files=True,
        include=["*.py"] + include,
        fix=["black"] + args,
        **kwargs,
    )


def PythonLint(args: List[str] = [], *, include: List[str] = [], **kwargs) -> BaseCheck:
    return Command(
        "PythonLint",
        ["flake8", "--max-line-length=88"] + args,
        pass_files=True,
        include=["*.py"] + include,
        **kwargs,
    )


def PythonImportOrder(
    args: List[str] = [], *, include: List[str] = [], **kwargs
) -> BaseCheck:
    return Command(
        "PythonImportOrder",
        ["isort", "-c"] + args,
        pass_files=True,
        include=["*.py"] + include,
        fix=["isort"] + args,
        **kwargs,
    )


def PythonTypes(
    args: List[str] = [], *, include: List[str] = [], **kwargs
) -> BaseCheck:
    return Command(
        "PythonTypes",
        ["mypy"] + args,
        pass_files=True,
        include=["*.py"] + include,
        **kwargs,
    )


def JavaScriptLint(*, include: List[str] = [], **kwargs) -> BaseCheck:
    return Command(
        "JavaScriptLint",
        ["npx", "eslint"],
        pass_files=True,
        include=["*.js"] + include,
        fix=["npx", "eslint", "--fix"],
        **kwargs,
    )


def RustFormat(args: List[str] = [], *, include: List[str] = [], **kwargs) -> BaseCheck:
    return Command(
        "RustFormat",
        ["cargo", "fmt", "--", "--check"] + args,
        pass_files=True,
        include=["*.rs"] + include,
        fix=["cargo", "fmt", "--"] + args,
        **kwargs,
    )
