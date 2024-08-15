import abc
import ast
import atexit
import os
import subprocess
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
    def check(self, changes: Changes) -> List[Failure]:
        raise NotImplementedError


class Precommit:
    def __init__(self) -> None:
        self.changes = _get_changes()
        self.num_failed_checks = 0

        atexit.register(self.atexit)

    def check(self, checker: BaseCheck, *, label: Optional[str] = None) -> None:
        failures = checker.check(self.changes)
        if len(failures) > 0:
            self.num_failed_checks += 1

        for failure in failures:
            self.print_failure(failure.message, label=label)

    def command(self, args: List[str], *, label: Optional[str] = None) -> None:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode != 0:
            self.num_failed_checks += 1
            self.print_failure(f"`{args[0]}` exited with non-zero return code")

    def print_failure(self, message: str, *, label: Optional[str] = None) -> None:
        label_or_not = f" {label}:" if label else ""
        print(f"{_red('fail:')}{label_or_not} {message}")

    def atexit(self):
        if self.num_failed_checks > 0:
            msg = _red(f"{self.failures} failed")
            print()
            print(f"{msg}. Commit aborted.")
            os._exit(1)


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m"


def _get_changes() -> Changes:
    added_files = _git_diff_filter("A")
    modified_files = _git_diff_filter("M")
    deleted_files = _git_diff_filter("D")
    return Changes(added_files=added_files, modified_files=modified_files, deleted_files=deleted_files)


def _git_diff_filter(filter_string):
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", f"--diff-filter={filter_string}"],
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
