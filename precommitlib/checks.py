"""
A suite of useful pre-commit checks.

If you want to write your own check, you'll need to create a new class that inherits
from `BaseCheck` and defines a `check` method that returns a `Problem` object if it
finds any issues, or `None` otherwise. Read through the existing checks in this module
for inspiration.

If your check can be formulated as a shell command, you can just write a function that
wraps the `Command` class. This module contains many examples of that.

Author:  Ian Fisher (iafisher@fastmail.com)
Version: May 2020
"""
import os
import shlex
import textwrap
from typing import List, Optional, Union

from . import utils
from .lib import (
    BaseCheck,
    Problem,
    UsageError,
    get_staged_files,
    get_unstaged_files,
    run,
)


class NoStagedAndUnstagedChanges(BaseCheck):
    """Checks that each staged file doesn't also have unstaged changes."""

    def check(self, files: List[str], *, stream_output: bool) -> Optional[Problem]:
        # This check is highly unusual in that it ignores the `files` parameter and
        # instead queries the state of the repository itself. Almost all other checks
        # should NOT do this.
        staged = get_staged_files()
        unstaged = get_unstaged_files()
        both = set(staged).intersection(set(unstaged))
        if both:
            message = "\n".join(sorted(both))
            if stream_output:
                _stream(message)
            return Problem(autofix=["git", "add"] + list(both))

        return None

    def is_fixable(self) -> bool:
        return True


# We construct it like this so the string literal doesn't trigger the check itself.
DO_NOT_SUBMIT = "DO NOT " + "SUBMIT"


class DoNotSubmit(BaseCheck):
    f"""Checks that files do not contain the string '{DO_NOT_SUBMIT}'."""

    def check(self, files: List[str], *, stream_output: bool) -> Optional[Problem]:
        bad_paths = []
        for path in files:
            with open(path, "rb") as f:
                if DO_NOT_SUBMIT.encode("ascii") in f.read().upper():
                    bad_paths.append(path)

        if bad_paths:
            message = "\n".join(sorted(bad_paths))
            if stream_output:
                _stream(message)
            return Problem(message=f"file contains '{DO_NOT_SUBMIT}'")

        return None


class NoWhitespaceInFilePath(BaseCheck):
    """Checks that file paths do not contain whitespace."""

    def check(self, files: List[str], *, stream_output: bool) -> Optional[Problem]:
        bad_paths = []
        for path in files:
            if any(c.isspace() for c in path):
                bad_paths.append(path)

        if bad_paths:
            message = "\n".join(sorted(bad_paths))
            if stream_output:
                _stream(message)
            return Problem(message="file path contains whitespace")

        return None


class Command(BaseCheck):
    def __init__(
        self,
        name: str,
        cmd: Union[List[str], str],
        fix: Optional[List[str]] = None,
        shell: bool = False,
        pass_files: bool = False,
        separately: bool = False,
        working_directory: str = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.name = name
        self.cmd = cmd
        self.fix = fix
        self.working_directory = working_directory

        if separately is True and pass_files is False:
            raise UsageError("if `separately` is True, `pass_files` must also be True")

        self.shell = shell
        self.pass_files = pass_files
        self.separately = separately

    def check(self, files: List[str], *, stream_output: bool) -> Optional[Problem]:
        if self.separately:
            problem = False
            for path in files:
                cmd: Union[List[str], str]
                if isinstance(self.cmd, str):
                    cmd = self.cmd + " " + shlex.quote(path)
                else:
                    cmd = self.cmd + [path]

                r = run(
                    cmd,
                    shell=self.shell,
                    stream_output=stream_output,
                    working_directory=self.working_directory,
                )
                if r.returncode != 0:
                    problem = True

            if problem:
                # TODO(2020-04-23): There should be a separate fix command for each
                # file path.
                return Problem(autofix=self.fix)
        else:
            args = files if self.pass_files else []
            if isinstance(self.cmd, str):
                cmd = self.cmd + " " + " ".join(map(shlex.quote, args))
            else:
                cmd = self.cmd + args

            r = run(
                cmd,
                shell=self.shell,
                stream_output=stream_output,
                working_directory=self.working_directory,
            )
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


def PipFreeze(venv, **kwargs):
    if venv is None:
        pip = "pip"
    else:
        pip = os.path.join(venv, "bin", "pip")

    return Command(
        "PipFreeze",
        f"[ ! -e requirements.txt ] || {pip} freeze | diff - requirements.txt",
        shell=True,
        **kwargs,
    )


def JavaScriptLint(*, include: List[str] = [], **kwargs) -> BaseCheck:
    return Command(
        "JavaScriptLint",
        ["npx", "eslint", "--max-warnings", "0"],
        pass_files=True,
        include=["*.js"] + include,
        fix=["npx", "eslint", "--fix"],
        **kwargs,
    )


def JavaScriptPrettierFormat(
    *, local_install=False, include: List[str] = [], **kwargs
) -> BaseCheck:
    cmd = ["npx", "prettier", "--check"] if local_install else ["prettier", "--check"]
    return Command(
        "JavaScriptPrettierFormat",
        cmd,
        pass_files=True,
        include=["*.js"] + include,
        fix=["npx", "prettier", "--write"],
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


def TypeScriptFormat(
    args: List[str] = [], *, include: List[str] = [], **kwargs
) -> BaseCheck:
    return Command(
        "TypeScriptFormat",
        ["tsfmt", "--verify"] + args,
        pass_files=True,
        include=["*.ts"] + include,
        fix=["tsfmt", "-r"],
        **kwargs,
    )


def _stream(msg: str) -> None:
    """
    Prints the message.

    This is the function that all checks should use to emit output, like this:

        if stream_output:
            _stream(msg)

    """
    print(textwrap.indent(msg, utils.blue("|  ")))
