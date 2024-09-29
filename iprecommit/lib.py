import atexit
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, NoReturn, Optional, Self, Tuple

from . import checks
from .checks import Changes


@dataclass
class CheckConfig:
    patterns: Optional[List[checks.Pattern]]
    name: Optional[str]


class Checks:
    checkers: List[Tuple[checks.Base, CheckConfig]]
    parent: "Pre"

    def __init__(self, parent: "Pre") -> None:
        self.checkers = []
        self.parent = parent

    def check(
        self,
        checker: checks.Base,
        *,
        patterns: Optional[List[checks.Pattern]] = None,
        name: Optional[str] = None,
    ) -> None:
        self.parent._validate_check_args(checker)
        if not isinstance(checker, checks.Base):
            raise IPrecommitError(
                "The argument to `check` must be a subclass of `checks.Base`."
            )

        self.checkers.append((checker, CheckConfig(patterns=patterns, name=name)))

    def sh(
        self,
        *cmd,
        pass_files: bool = False,
        base_pattern: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        if name is None:
            name = " ".join(map(shlex.quote, cmd))

        return self.check(
            checks.ShellCommandPasses(
                cmd,
                pass_files=pass_files,
                base_pattern=base_pattern,
            ),
            name=name,
        )


class CommitMsgChecks:
    checkers: List[checks.CommitMsg]
    parent: "Pre"

    def __init__(self, parent: "Pre") -> None:
        self.checkers = []
        self.parent = parent

    def check(self, checker: checks.CommitMsg) -> None:
        self.parent._validate_check_args(checker)
        if not isinstance(checker, checks.CommitMsg):
            raise IPrecommitError(
                "The argument to `check` must be a subclass of `checks.CommitMsg`."
            )

        self.checkers.append(checker)


@dataclass
class CLIArgs:
    hook_name: str
    unstaged: bool
    fix_mode: bool
    commit_msg: Optional[str]
    remote: Optional[str]

    def serialize(self) -> List[str]:
        subcmd = "fix" if self.fix_mode else "run"
        if self.hook_name == "commit-msg":
            assert self.commit_msg is not None
            return [subcmd, self.hook_name, self.commit_msg]
        elif self.hook_name == "pre-push":
            assert self.remote is not None
            return [subcmd, self.hook_name, self.remote]
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
        if hook_name not in ("pre-commit", "pre-push", "commit-msg"):
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
                remote=None,
            )
        elif hook_name == "pre-push":
            if len(args) < 3:
                raise IPrecommitError

            return cls(
                hook_name=hook_name,
                unstaged=False,
                fix_mode=fix_mode,
                commit_msg=None,
                remote=args[2],
            )
        else:
            unstaged = "--unstaged" in flags
            return cls(
                hook_name=hook_name,
                unstaged=unstaged,
                fix_mode=fix_mode,
                commit_msg=None,
                remote=None,
            )


class Pre:
    num_failed_checks: int
    called_main: bool
    commit: Checks
    push: Checks
    commit_msg: CommitMsgChecks

    def __init__(self) -> None:
        self.num_failed_checks = 0
        self.called_main = False

        self.commit = Checks(self)
        self.push = Checks(self)
        self.commit_msg = CommitMsgChecks(self)

        atexit.register(self._atexit)

    def main(self) -> None:
        self.called_main = True
        args = self._parse_args()
        if args.hook_name == "pre-commit":
            self._main_pre_commit(args)
        elif args.hook_name == "commit-msg":
            self._main_commit_msg(args)
        elif args.hook_name == "pre-push":
            self._main_pre_push(args)
        else:
            raise IPrecommitImpossibleError()

    def _main_pre_commit(self, args: CLIArgs) -> None:
        all_changes = _get_git_changes(include_unstaged=args.unstaged)
        self._main_pre(args, self.commit.checkers, all_changes)
        if not args.fix_mode:
            self._summary("Commit")

    def _main_pre_push(self, args: CLIArgs) -> None:
        assert args.remote is not None
        current_branch = _get_git_current_branch()
        last_commit_pushed = _get_git_last_commit_pushed(args.remote, current_branch)
        all_changes = _get_git_changes(include_unstaged=False, since=last_commit_pushed)
        self._main_pre(args, self.push.checkers, all_changes)
        self._summary("Push")

    def _main_pre(
        self,
        args: CLIArgs,
        checkers: List[Tuple[checks.Base, CheckConfig]],
        all_changes: checks.Changes,
    ) -> None:
        for checker, config in checkers:
            name = config.name or checker.__class__.__name__

            changes = all_changes.filter(
                checker.base_pattern(), checker.patterns() + (config.patterns or [])
            )
            if changes.empty():
                self._print_status(name, yellow("skipped"))
                continue

            if args.fix_mode:
                self._fix(checker, changes, name)
                continue

            self._print_status(name, "running")
            if not checker.check(changes):
                self._print_status(name, red("failed"))
                self.num_failed_checks += 1
            else:
                self._print_status(name, green("passed"))

            print()
            print()

    def _main_commit_msg(self, args: CLIArgs) -> None:
        assert args.commit_msg is not None
        try:
            text = Path(args.commit_msg).read_text()
        except FileNotFoundError as e:
            raise IPrecommitError("could not read commit message file") from e

        for checker in self.commit_msg.checkers:
            name = checker.__class__.__name__

            self._print_status(name, "running")
            if not checker.check(text):
                self._print_status(name, red("failed"))
                self.num_failed_checks += 1
            else:
                self._print_status(name, green("passed"))

            print()
            print()

        if not args.fix_mode:
            self._summary("Commit")

    def _summary(self, action: str) -> None:
        if self.num_failed_checks > 0:
            s = f"{self.num_failed_checks} failed"
            print(f"{red(s)}. {action} aborted.")
            sys.stdout.flush()
            sys.exit(1)

    def _fix(self, checker: checks.Base, changes: Changes, name: str) -> None:
        if not hasattr(checker, "fix"):
            return

        self._print_status(name, "fixing")
        checker.fix(changes)
        self._print_status(name, "finished")

    def _print_status(self, name: str, status: str) -> None:
        print(f"{cyan('[iprecommit]')} {name}: {status}")

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
        argv = sys.argv[1:]
        try:
            return CLIArgs.deserialize(argv)
        except IPrecommitError:
            bail(
                "precommit.py should not be run directly. Use `iprecommit run` instead."
            )

    def _atexit(self) -> None:
        if not self.called_main:
            warn(
                f"The pre-commit hook exited without running. Did you forget to call `{self.__class__.__name__}.main()`?"
            )
            sys.stdout.flush()
            # use _exit() to avoid recursively invoking ourselves as an atexit hook
            os._exit(1)


def _get_git_current_branch() -> str:
    # TODO: can a git branch name be non-UTF8?
    result = subprocess.run(
        ["git", "branch", "--show-current"], capture_output=True, text=True
    )
    return result.stdout.strip()


def _get_git_last_commit_pushed(remote: str, branch: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", f"{remote}/{branch}"], capture_output=True, text=True
    )
    if result.returncode == 0:
        return result.stdout.strip()
    else:
        # the empty commit allows us to diff from beginning of git history
        # this is the case when no commits have been pushed to the remote
        return _get_git_diff_empty_commit()


def _get_git_diff_empty_commit() -> str:
    # courtesy of https://stackoverflow.com/questions/40883798
    # TODO: handle error code
    result = subprocess.run(
        ["git", "hash-object", "-t", "tree", "/dev/null"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _get_git_changes(*, include_unstaged: bool, since: Optional[str] = None) -> Changes:
    added_paths = _git_diff_filter("A", include_unstaged=include_unstaged, since=since)
    modified_paths = _git_diff_filter(
        "M", include_unstaged=include_unstaged, since=since
    )
    deleted_paths = _git_diff_filter(
        "D", include_unstaged=include_unstaged, since=since
    )
    return Changes(
        added_paths=added_paths,
        modified_paths=modified_paths,
        deleted_paths=deleted_paths,
    )


def _git_diff_filter(
    filter_string, *, include_unstaged: bool, since: Optional[str] = None
):
    if since is not None:
        ref = since
    elif include_unstaged:
        ref = "HEAD"
    else:
        ref = "--cached"

    result = subprocess.run(
        ["git", "diff", ref, "--name-only", f"--diff-filter={filter_string}", "-z"],
        capture_output=True,
    )
    return [Path(os.fsdecode(p)) for p in result.stdout.split(b"\x00") if p]


def bail(msg: str) -> NoReturn:
    print(f"{red('Error')}: {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg: str) -> None:
    print(f"{yellow('Warning')}: {msg}", file=sys.stderr)


ENV_HOOK_PATH = "IPRECOMMIT_HOOK_PATH"


def red(s: str) -> str:
    return _colored(s, 31)


def yellow(s: str) -> str:
    return _colored(s, 33)


def cyan(s: str) -> str:
    return _colored(s, 36)


def green(s: str) -> str:
    return _colored(s, 32)


def _colored(s: str, code: int) -> str:
    if not _has_color():
        return s

    return f"\033[{code}m{s}\033[0m"


# don't access directly; use _has_color() instead
#
# once set, this may be reset back to `None` if the module is re-imported elsewhere
_COLOR = None


def _has_color() -> bool:
    global _COLOR

    if _COLOR is not None:
        return _COLOR

    _COLOR = not (
        # https://no-color.org/
        "NO_COLOR" in os.environ
        or not os.isatty(sys.stdout.fileno())
        or not os.isatty(sys.stderr.fileno())
    )

    return _COLOR


class IPrecommitError(Exception):
    pass


# Not a subclass of `IPrecommitError` so we don't accidentally catch it.
class IPrecommitImpossibleError(Exception):
    def __init__(self) -> None:
        super().__init__(
            "This error should never happen. If you see it, please contact an iprecommit developer."
        )
