import ast
import atexit
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, NoReturn, Optional, Tuple

from . import checks
from .checks import Changes


@dataclass
class PreCommitConfig:
    patterns: Optional[List[checks.Pattern]]


class PreCommitChecks:
    checkers: List[Tuple[checks.BasePreCommit, PreCommitConfig]]
    parent: "Pre"

    def __init__(self, parent: "Pre") -> None:
        self.checkers = []
        self.parent = parent

    # TODO: `skip` argument
    def check(
        self,
        checker: checks.BasePreCommit,
        *,
        patterns: Optional[List[checks.Pattern]] = None,
    ) -> None:
        if isinstance(checker, type):
            raise IPrecommitError(
                "You passed a class to `check`, not an object. Did you forget the parentheses?"
            )

        if self.parent.called_main:
            raise IPrecommitError(
                "You called `check` after `main`. This check will never be run."
            )

        self.checkers.append((checker, PreCommitConfig(patterns=patterns)))

    def sh(
        self, *cmd, pass_files: bool = False, base_pattern: Optional[str] = None
    ) -> None:
        return self.check(
            checks.ShellCommandPasses(
                cmd, pass_files=pass_files, base_pattern=base_pattern
            )
        )


@dataclass
class CLIArgs:
    hook_name: str
    unstaged: bool
    fix_mode: bool


class Pre:
    num_failed_checks: int
    called_main: bool
    commit: PreCommitChecks

    def __init__(self) -> None:
        self.num_failed_checks = 0
        self.called_main = False

        self.commit = PreCommitChecks(self)

        atexit.register(self._atexit)

    def main(self) -> None:
        self.called_main = True
        args = self._parse_args()
        if args.hook_name == "pre-commit":
            self._main_pre_commit(args)
        else:
            raise IPrecommitImpossibleError()

    def _main_pre_commit(self, args: CLIArgs) -> None:
        all_changes = _get_git_changes(include_unstaged=args.unstaged)

        for checker, config in self.commit.checkers:
            changes = all_changes.filter(
                checker.base_pattern(), checker.patterns() + (config.patterns or [])
            )
            if changes.empty():
                self._skipped(checker.name())
                return

            if args.fix_mode:
                self._fix(checker, changes)
                return

            # TODO: colored output
            print(f"iprecommit: {checker.name()}: running")
            if not checker.check(changes):
                print(f"iprecommit: {checker.name()}: failed")
                self.num_failed_checks += 1
            else:
                print(f"iprecommit: {checker.name()}: passed")

        if not args.fix_mode and self.num_failed_checks > 0:
            # TODO: colored output
            print()
            print(f"{self.num_failed_checks} failed. Commit aborted.")
            sys.stdout.flush()
            sys.exit(1)

    def _fix(self, checker: checks.BasePreCommit, changes: Changes) -> None:
        if not hasattr(checker, "fix"):
            self._skipped(checker.name())
            return

        print(f"iprecommit: {checker.name()}: fixing")
        checker.fix(changes)
        print(f"iprecommit: {checker.name()}: finished")

    def _skipped(self, name: str) -> None:
        print(f"iprecommit: {name}: skipped")

    def _parse_args(self) -> CLIArgs:
        # since precommit.py is meant to be invoked through `iprecommit run`, we only do minimal
        # error-checking here (e.g., we ignore unknown arguments), assuming that `iprecommit` will
        # pass us something valid

        argv = sys.argv[1:]
        if not len(argv) >= 2:
            self._cli_args_error()

        hook_name = argv[0]
        subcmd = argv[1]
        flags = argv[2:]

        if hook_name not in ("pre-commit",):
            self._cli_args_error()

        if subcmd not in ("run", "fix"):
            self._cli_args_error()

        fix_mode = subcmd == "fix"
        unstaged = "--unstaged" in flags
        return CLIArgs(hook_name=hook_name, unstaged=unstaged, fix_mode=fix_mode)

    def _cli_args_error(self) -> NoReturn:
        bail("precommit.py should not be run directly. Use `iprecommit run` instead.")

    def _atexit(self) -> None:
        if not self.called_main:
            warn(
                f"The pre-commit hook exited without running. Did you forget to call `{self.__class__.__name__}.main()`?"
            )
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


# TODO: these no longer need to be shared and can be moved back to `main.py`
def _add_run_flags(argparser):
    argparser.add_argument("--unstaged", action="store_true")


def _add_fix_flags(argparser):
    argparser.add_argument("--unstaged", action="store_true")


def bail(msg: str) -> NoReturn:
    # TODO: color
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg: str) -> None:
    # TODO: color
    print(f"Warning: {msg}", file=sys.stderr)


ENV_HOOK_PATH = "IPRECOMMIT_HOOK_PATH"


class IPrecommitError(Exception):
    pass


# Not a subclass of `IPrecommitError` so we don't accidentally catch it.
class IPrecommitImpossibleError(Exception):
    def __init__(self) -> None:
        super().__init__(
            "This error should never happen. If you see it, please contact an iprecommit developer."
        )
