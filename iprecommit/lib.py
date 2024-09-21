import argparse
import ast
import atexit
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from . import checks
from .checks import Changes


class Precommit:
    num_failed_checks: int
    unstaged: bool
    fix_mode: bool

    def __init__(self) -> None:
        self.num_failed_checks = 0
        self.unstaged = False
        self.fix_mode = False

        self._parse_args()
        self.changes = _get_git_changes(include_unstaged=self.unstaged)

        atexit.register(self._atexit)

    # TODO: `skip` argument
    def check(
        self, checker: checks.Base, *, patterns: Optional[List[checks.Pattern]] = None
    ) -> None:
        changes = self.changes.filter(
            checker.base_pattern(), checker.patterns() + (patterns or [])
        )
        if changes.empty():
            self._skipped(checker.name())
            return

        if self.fix_mode:
            self._fix(checker, changes)
            return

        # TODO: colored output
        print(f"iprecommit: {checker.name()}: running")
        if not checker.check(changes):
            print(f"iprecommit: {checker.name()}: failed")
            self.num_failed_checks += 1
        else:
            print(f"iprecommit: {checker.name()}: passed")

    def sh(self, *cmd, pass_files: bool = False, base_pattern: Optional[str] = None) -> None:
        return self.check(checks.ShellCommandPasses(cmd, pass_files=pass_files, base_pattern=base_pattern))

    def _fix(self, checker: checks.Base, changes: Changes) -> None:
        if not hasattr(checker, "fix"):
            self._skipped(checker.name())
            return

        print(f"iprecommit: {checker.name()}: fixing")
        checker.fix(changes)
        print(f"iprecommit: {checker.name()}: finished")

    def _skipped(self, name: str) -> str:
        print(f"iprecommit: {name}: skipped")

    def _parse_args(self) -> None:
        argparser = argparse.ArgumentParser()
        argparser.set_defaults(subcmd="")
        subparsers = argparser.add_subparsers()

        # TODO: these 4 lines should be shared with main.py
        argparser_run = _create_subparser(subparsers, "run")
        _add_run_flags(argparser_run)

        argparser_fix = _create_subparser(subparsers, "fix")
        _add_fix_flags(argparser_fix)

        args = argparser.parse_args()

        if args.subcmd == "run":
            self.unstaged = args.unstaged
        elif args.subcmd == "fix":
            self.unstaged = args.unstaged
            self.fix_mode = True
        else:
            argparser.print_usage()
            sys.exit(1)

    def _atexit(self) -> None:
        if not self.fix_mode and self.num_failed_checks > 0:
            # TODO: colored output
            print()
            print(f"{self.num_failed_checks} failed. Commit aborted.")
            sys.stdout.flush()
            # use _exit() to avoid recursively invoking ourselves as an atexit hook
            os._exit(1)


def _get_git_changes(*, include_unstaged: bool) -> Changes:
    added_paths = _git_diff_filter("A", include_unstaged=include_unstaged)
    modified_paths = _git_diff_filter("M", include_unstaged=include_unstaged)
    deleted_paths = _git_diff_filter("D", include_unstaged=include_unstaged)
    return Changes(
        added_paths=added_paths,
        modified_paths=modified_paths,
        deleted_paths=deleted_paths,
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
    # TODO: find the code in git that does this
    if path.startswith('"') and path.endswith('"'):
        # TODO(2020-04-16): Do I need to add "b" and then decode, or can I just eval?
        # TODO: less hacky way to do this?
        return Path(ast.literal_eval("b" + path).decode("utf-8"))
    else:
        return Path(path)


def _create_subparser(subparsers, name):
    argparser = subparsers.add_parser(name)
    argparser.set_defaults(subcmd=name)
    return argparser


def _add_run_flags(argparser):
    argparser.add_argument("--unstaged", action="store_true")


def _add_fix_flags(argparser):
    argparser.add_argument("--unstaged", action="store_true")


class IPrecommitError(Exception):
    pass
