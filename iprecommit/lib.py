import abc
import ast
import atexit
import os
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional


@dataclass
class Changes:
    added_files: List[Path]
    modified_files: List[Path]
    deleted_files: List[Path]


@dataclass
class Failure:
    message: str


class BaseCheck(abc.ABC):
    @abc.abstractmethod
    def check(self, changes: Changes) -> List[Failure]:
        pass


class Precommit:
    def __init__(self) -> None:
        include_unstaged = os.environ.get("IPRECOMMIT_UNSTAGED") == "1"
        self.changes = _get_changes(include_unstaged=include_unstaged)
        self.num_failed_checks = 0

        atexit.register(self.atexit)

    def check(self, checker: BaseCheck, *, label: str = "") -> None:
        failures = checker.check(self.changes)
        if len(failures) > 0:
            self.num_failed_checks += 1
            self.print_failure(
                label or checker.__class__.__name__,
                "\n".join(f.message for f in failures),
            )

    def command(self, args: List[str], *, label: str = "") -> None:
        result = subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        if result.returncode != 0:
            self.num_failed_checks += 1
            self.print_failure(" ".join(args), result.stdout)

    def print_failure(self, label: str, message: str) -> None:
        print(f"{red('failed:')} {label}")
        if message:
            print(textwrap.indent(message, "  "))

    def atexit(self):
        if self.num_failed_checks > 0:
            msg = red(f"{self.num_failed_checks} failed")
            print()
            print(f"{msg}. Commit aborted.")
            os._exit(1)


def red(s: str) -> str:
    return f"\033[31m{s}\033[0m"


def yellow(s):
    return f"\033[33m{s}\033[0m"


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