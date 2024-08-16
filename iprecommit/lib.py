import abc
import ast
import atexit
import fnmatch
import os
import shlex
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import List, Union


@dataclass
class Changes:
    added_files: List[Path]
    modified_files: List[Path]
    deleted_files: List[Path]

    def filtered(
        self, patterns: List[str], *, exclude: List[str], include_deleted: bool = True
    ) -> "Changes":
        return Changes(
            added_files=_apply_filter(self.added_files, patterns, exclude),
            modified_files=_apply_filter(self.modified_files, patterns, exclude),
            deleted_files=(
                _apply_filter(self.deleted_files, patterns, exclude)
                if include_deleted
                else []
            ),
        )

    def is_empty(self) -> bool:
        return (
            len(self.added_files) == 0
            and len(self.modified_files) == 0
            and len(self.deleted_files) == 0
        )

    def as_list(self) -> List[Path]:
        return self.added_files + self.modified_files + self.deleted_files


def _apply_filter(
    files: List[Path], pattern_list: List[str], exclude_list: List[str]
) -> List[Path]:
    r = [
        f
        for f in files
        if not pattern_list or any(fnmatch.fnmatch(f, p) for p in pattern_list)
    ]
    r = [
        f
        for f in r
        if not exclude_list or all(not fnmatch.fnmatch(f, p) for p in exclude_list)
    ]
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

    def check(
        self,
        checker: BaseCheck,
        *,
        pattern: List[str] = [],
        exclude: List[str] = [],
        label: str = "",
    ) -> None:
        if not label:
            label = checker.__class__.__name__

        if self.in_fix_mode:
            self._fix(checker, label=label)
            return

        changes = self.changes.filtered(pattern, exclude=exclude)
        if changes.is_empty():
            self.print_skipped(label)
            return

        messages = checker.check(changes)

        if len(messages) > 0:
            self.num_failed_checks += 1
            self.print_failure(label, "\n".join(m.message for m in messages))
        else:
            self.print_success(label)

    def _fix(self, checker: BaseCheck, *, label: str) -> None:
        messages = checker.fix(self.changes)
        for m in messages:
            self.print_fix(label, m.path)

    def command(
        self,
        args: List[str],
        *,
        pass_files: bool = False,
        pattern: List[str] = [],
        exclude: List[str] = [],
        label: str = "",
    ) -> None:
        if not label:
            label = " ".join(shlex.quote(str(a)) for a in args)

        if pass_files:
            changes = self.changes.filtered(
                pattern, exclude=exclude, include_deleted=False
            )
            if changes.is_empty():
                self.print_skipped(label)
                return

            args.extend(changes.as_list())

        result = subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        if result.returncode != 0:
            self.num_failed_checks += 1
            self.print_failure(label, result.stdout)
        else:
            self.print_success(label)

    def print_failure(self, label: str, message: str) -> None:
        print(f"{red('failed:')} {label}")
        if message:
            print(textwrap.indent(message, "  "))
            print()

    def print_success(self, label: str) -> None:
        print(f"{green('passed:')} {label}")

    def print_skipped(self, label: str) -> None:
        print(f"{yellow('skipped:')} {label}")

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


def green(s: str) -> str:
    return f"\033[32m{s}\033[0m"


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
