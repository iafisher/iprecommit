import ast
import atexit
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, NoReturn, Optional, Self, Tuple

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
        self.parent._validate_check_args(checker)
        self.checkers.append((checker, PreCommitConfig(patterns=patterns)))

    def sh(
        self, *cmd, pass_files: bool = False, base_pattern: Optional[str] = None
    ) -> None:
        return self.check(
            checks.ShellCommandPasses(
                cmd, pass_files=pass_files, base_pattern=base_pattern
            )
        )


class CommitMsgChecks:
    checkers: List[checks.BaseCommitMsg]
    parent: "Pre"

    def __init__(self, parent: "Pre") -> None:
        self.checkers = []
        self.parent = parent

    # TODO: `skip` argument
    def check(self, checker: checks.BaseCommitMsg) -> None:
        self.parent._validate_check_args(checker)
        self.checkers.append(checker)


@dataclass
class CLIArgs:
    hook_name: str
    unstaged: bool
    fix_mode: bool
    commit_msg: Optional[str]

    def serialize(self) -> List[str]:
        subcmd = "fix" if self.fix_mode else "run"
        if self.hook_name == "commit-msg":
            assert self.commit_msg is not None
            return [subcmd, self.hook_name, self.commit_msg]
        else:
            return [subcmd, self.hook_name] + (["--unstaged"] if self.unstaged else [])

    @classmethod
    def deserialize(cls, args: List[str]) -> Self:
        # since precommit.py is meant to be invoked through `iprecommit run`, we only do minimal
        # error-checking here (e.g., we ignore unknown arguments), assuming that `iprecommit` will
        # pass us something valid

        if len(args) < 2:
            raise IPrecommitError

        subcmd = args[0]
        hook_name = args[1]
        flags = args[2:]

        if subcmd not in ("run", "fix"):
            raise IPrecommitError

        # TODO: define in one place the valid git hooks
        if hook_name not in ("pre-commit", "commit-msg"):
            raise IPrecommitError

        fix_mode = subcmd == "fix"
        if hook_name == "commit-msg":
            if len(args) < 3:
                raise IPrecommitError

            return cls(
                hook_name=hook_name,
                unstaged=False,
                fix_mode=fix_mode,
                commit_msg=args[2],
            )
        else:
            unstaged = "--unstaged" in flags
            return cls(
                hook_name=hook_name,
                unstaged=unstaged,
                fix_mode=fix_mode,
                commit_msg=None,
            )


class Pre:
    num_failed_checks: int
    called_main: bool
    commit: PreCommitChecks
    commit_msg: CommitMsgChecks

    def __init__(self) -> None:
        self.num_failed_checks = 0
        self.called_main = False

        self.commit = PreCommitChecks(self)
        self.commit_msg = CommitMsgChecks(self)

        atexit.register(self._atexit)

    def main(self) -> None:
        self.called_main = True
        args = self._parse_args()
        if args.hook_name == "pre-commit":
            self._main_pre_commit(args)
        elif args.hook_name == "commit-msg":
            self._main_commit_msg(args)
        else:
            raise IPrecommitImpossibleError()

    def _main_pre_commit(self, args: CLIArgs) -> None:
        all_changes = _get_git_changes(include_unstaged=args.unstaged)

        for checker, config in self.commit.checkers:
            changes = all_changes.filter(
                checker.base_pattern(), checker.patterns() + (config.patterns or [])
            )
            if changes.empty():
                self._print_status(checker, "skipped")
                continue

            if args.fix_mode:
                self._fix(checker, changes)
                continue

            self._print_status(checker, "running")
            if not checker.check(changes):
                self._print_status(checker, "failed")
                self.num_failed_checks += 1
            else:
                self._print_status(checker, "passed")

        if not args.fix_mode:
            self._summary()

    def _main_commit_msg(self, args: CLIArgs) -> None:
        assert args.commit_msg is not None
        try:
            text = Path(args.commit_msg).read_text()
        except FileNotFoundError as e:
            raise IPrecommitError("could not read commit message file") from e

        for checker in self.commit_msg.checkers:
            self._print_status(checker, "running")
            if not checker.check(text):
                self._print_status(checker, "failed")
                self.num_failed_checks += 1
            else:
                self._print_status(checker, "passed")

        if not args.fix_mode:
            self._summary()

    def _summary(self) -> None:
        if self.num_failed_checks > 0:
            # TODO: colored output
            print()
            print(f"{self.num_failed_checks} failed. Commit aborted.")
            sys.stdout.flush()
            sys.exit(1)

    def _fix(self, checker: checks.BasePreCommit, changes: Changes) -> None:
        if not hasattr(checker, "fix"):
            self._print_status(checker, "skipped")
            return

        self._print_status(checker, "fixing")
        checker.fix(changes)
        self._print_status(checker, "finished")

    def _print_status(self, checker: checks.Base, status: str) -> None:
        # TODO: colored output
        print(f"iprecommit: {checker.name()}: {status}")

    def _validate_check_args(self, checker: Any) -> None:
        if isinstance(checker, type):
            raise IPrecommitError(
                "You passed a class to `check`, not an object. Did you forget the parentheses?"
            )

        if self.called_main:
            raise IPrecommitError(
                "You called `check` after `main`. This check will never be run."
            )

    def _parse_args(self) -> CLIArgs:
        argv = sys.argv[1:]
        try:
            return CLIArgs.deserialize(argv)
        except IPrecommitError:
            bail(
                "precommit.py should not be run directly. Use `iprecommit run` instead."
            )

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
