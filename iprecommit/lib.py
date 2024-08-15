import abc
import ast
import atexit
import fnmatch
import os
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class Changes:
    added_files: List[Path]
    modified_files: List[Path]
    deleted_files: List[Path]

    def filter(self, pattern: str) -> List[Path]:
        r = self.added_files + self.modified_files
        if pattern:
            r = [p for p in r if fnmatch.fnmatch(p, pattern)]
        return r


@dataclass
class Message:
    message: str
    path: Path


class BaseCheck(abc.ABC):
    @abc.abstractmethod
    def check(self, changes: Changes) -> List[Message]:
        pass

    def fix(self, changes: Changes) -> List[Message]:
        return []


class Precommit:
    def __init__(self) -> None:
        iprecommit_unstaged = os.environ.get("IPRECOMMIT_UNSTAGED") == "1"
        iprecommit_fix = os.environ.get("IPRECOMMIT_FIX") == "1"

        self.in_fix_mode = iprecommit_fix
        self.changes = _get_changes(include_unstaged=iprecommit_unstaged)
        self.num_failed_checks = 0

        atexit.register(self.atexit)

    def check(self, checker: BaseCheck, *, label: str = "") -> None:
        if self.in_fix_mode:
            self._fix(checker, label=label)
            return

        messages = checker.check(self.changes)
        if len(messages) > 0:
            self.num_failed_checks += 1
            self.print_failure(
                label or checker.__class__.__name__,
                "\n".join(m.message for m in messages),
            )

    def _fix(self, checker: BaseCheck, *, label: str = "") -> None:
        messages = checker.fix(self.changes)
        for m in messages:
            self.print_fix(label or checker.__class__.__name__, m.path)

    def command(
        self,
        args: List[str],
        *,
        pass_files: bool = False,
        pattern: str = "",
        label: str = "",
    ) -> None:
        if pass_files:
            files = self.changes.filter(pattern)
            if len(files) == 0:
                return

            args.extend(files)

        result = subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        if result.returncode != 0:
            self.num_failed_checks += 1
            self.print_failure(label or " ".join(map(str, args)), result.stdout)

    def print_failure(self, label: str, message: str) -> None:
        print(f"{red('failed:')} {label}")
        if message:
            print(textwrap.indent(message, "  "))
            print()

    def print_fix(self, label: str, path: Path) -> None:
        print(f"{cyan('fixed:')} {label}: {path}")

    def atexit(self):
        if self.num_failed_checks > 0:
            msg = red(f"{self.num_failed_checks} failed")
            print()
            print(f"{msg}. Commit aborted.")
            os._exit(1)


def red(s: str) -> str:
    return f"\033[31m{s}\033[0m"


def yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m"


def cyan(s: str) -> str:
    return f"\033[36m{s}\033[0m"


def _get_changes(*, include_unstaged: bool) -> Changes:
    added_files = _git_diff_filter("A", include_unstaged=include_unstaged)
    modified_files = _git_diff_filter("M", include_unstaged=include_unstaged)
    deleted_files = _git_diff_filter("D", include_unstaged=include_unstaged)
    return Changes(
        added_files=added_files,
        modified_files=modified_files,
        deleted_files=deleted_files,
    )


def _git_diff_filter(filter_string, *, include_unstaged: bool):
    result = subprocess.run(
        [
            "git",
            "diff",
            "HEAD" if include_unstaged else "--cached",
            "--name-only",
            f"--diff-filter={filter_string}",
        ],
        capture_output=True,
    )
    return [_decode_git_path(p) for p in result.stdout.decode("ascii").splitlines()]


def _decode_git_path(path):
    # If the file path contains a non-ASCII character or a literal double quote, Git
    # backslash-escapes the offending character and encloses the whole path in double
    # quotes. This function reverses that transformation and decodes the resulting bytes
    # as UTF-8.
    if path.startswith('"') and path.endswith('"'):
        # TODO(2020-04-16): Do I need to add "b" and then decode, or can I just eval?
        return Path(ast.literal_eval("b" + path).decode("utf-8"))
    else:
        return Path(path)
