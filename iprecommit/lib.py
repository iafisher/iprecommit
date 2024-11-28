import atexit
import fnmatch
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, NoReturn, Optional, Tuple, Union

from .exceptions import IPrecommitError, IPrecommitImpossibleError


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
    def deserialize(cls, args: List[str]) -> "CLIArgs":
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


@dataclass
class PreCommitCheck:
    name: Optional[str]
    cmd: List[str]
    fix: List[str]
    pass_files: bool
    filters: List[str]


@dataclass
class PrePushCheck:
    name: Optional[str]
    cmd: List[str]


@dataclass
class CommitMsgCheck:
    name: Optional[str]
    cmd: List[str]


def get_check_name(check: Union[PreCommitCheck, PrePushCheck, CommitMsgCheck]) -> str:
    if check.name is not None:
        return check.name
    else:
        return " ".join(map(shlex.quote, check.cmd))


class Checks:
    called_run: bool
    num_failed_checks: int
    pre_commit_checks: List[PreCommitCheck]
    pre_push_checks: List[PrePushCheck]
    commit_msg_checks: List[CommitMsgCheck]

    def __init__(self) -> None:
        self.called_run = False
        self.num_failed_checks = 0
        self.pre_commit_checks = []
        self.pre_push_checks = []
        self.commit_msg_checks = []

        atexit.register(self._atexit)

    def pre_commit(
        self,
        *cmd,
        pass_files: bool = True,
        filters: List[str] = [],
        fix: List[str] = [],
        name: Optional[str] = None,
    ) -> None:
        self.pre_commit_checks.append(
            PreCommitCheck(
                cmd=list(cmd),
                fix=fix,
                pass_files=pass_files,
                filters=filters,
                name=name,
            )
        )

    def pre_push(self, *cmd, name: Optional[str] = None) -> None:
        self.pre_push_checks.append(PrePushCheck(cmd=list(cmd), name=name))

    def commit_msg(self, *cmd, name: Optional[str] = None) -> None:
        self.commit_msg_checks.append(CommitMsgCheck(cmd=list(cmd), name=name))

    def run(self) -> None:
        self.called_run = True
        args = self._parse_args()
        if args.hook_name == "pre-commit":
            self._run_pre_commit(args)
        elif args.hook_name == "commit-msg":
            self._run_commit_msg(args)
        elif args.hook_name == "pre-push":
            self._run_pre_push(args)
        else:
            raise IPrecommitImpossibleError()

    def _run_pre_commit(self, args: CLIArgs) -> None:
        all_changed_paths = _get_git_changes(include_unstaged=args.unstaged)
        for check in self.pre_commit_checks:
            name = get_check_name(check)

            filtered_changed_paths = _filter_paths(all_changed_paths, check.filters)
            if not filtered_changed_paths:
                self._print_status(name, yellow("skipped"))
                continue

            if args.fix_mode:
                if check.fix:
                    self._print_status(name, "fixing")
                    cmd = check.fix
                    if check.pass_files:
                        cmd += filtered_changed_paths  # type: ignore
                    proc = subprocess.run(cmd)
                    if proc.returncode != 0:
                        # TODO: test for fix failed
                        self._print_status(name, red("fix failed"))
                    else:
                        self._print_status(name, "finished")
                else:
                    continue
            else:
                self._print_status(name, "running")
                cmd = check.cmd
                # TODO: test where pass_files=False
                if check.pass_files:
                    cmd += filtered_changed_paths  # type: ignore
                proc = subprocess.run(cmd)
                if proc.returncode != 0:
                    self._print_status(name, red("failed"))
                    self.num_failed_checks += 1
                else:
                    self._print_status(name, green("passed"))
            print()
            print()

        self._summary("Commit")

    def _run_commit_msg(self, args: CLIArgs) -> None:
        # TODO: check that fix_mode is False?
        assert args.commit_msg is not None

        for check in self.commit_msg_checks:
            name = get_check_name(check)

            self._print_status(name, "running")
            proc = subprocess.run(check.cmd + [args.commit_msg])
            if proc.returncode != 0:
                self._print_status(name, red("failed"))
                self.num_failed_checks += 1
            else:
                self._print_status(name, green("passed"))

            print()
            print()

        self._summary("Commit")

    def _run_pre_push(self, args: CLIArgs) -> None:
        assert args.remote is not None
        current_branch = _get_git_current_branch()
        last_commit_pushed = _get_git_last_commit_pushed(args.remote, current_branch)
        commits = _get_git_commits(since=last_commit_pushed)

        for check in self.pre_push_checks:
            name = get_check_name(check)

            self._print_status(name, "running")
            proc = subprocess.run(check.cmd + commits)
            if proc.returncode != 0:
                self._print_status(name, red("failed"))
                self.num_failed_checks += 1
            else:
                self._print_status(name, green("passed"))

            print()
            print()

        self._summary("Push")

    def _summary(self, action: str) -> None:
        if self.num_failed_checks > 0:
            s = f"{self.num_failed_checks} failed"
            print(f"{red(s)}. {action} aborted.")
            sys.stdout.flush()
            sys.exit(1)

    def _print_status(self, name: str, status: str) -> None:
        print(f"{cyan('[iprecommit]')} {name}: {status}")
        sys.stdout.flush()

    def _parse_args(self) -> CLIArgs:
        argv = sys.argv[1:]
        try:
            return CLIArgs.deserialize(argv)
        except IPrecommitError:
            bail(
                "precommit.py should not be run directly. Use `iprecommit run` instead."
            )

    def _atexit(self) -> None:
        if not self.called_run:
            warn(
                f"The pre-commit hook exited without running. Did you forget to call `{self.__class__.__name__}.run()`?"
            )
            sys.stdout.flush()
            # use _exit() to avoid recursively invoking ourselves as an atexit hook
            os._exit(1)


def _filter_paths(paths: List[Path], filters: List[str]) -> List[Path]:
    if not filters:
        return paths

    compiled_filters = [_compile_filter(f) for f in filters]

    base_filter = compiled_filters[0]
    compiled_filters = compiled_filters[1:]

    pairs: Iterable[Tuple[Path, bool]] = (base_filter((path, False)) for path in paths)
    for f in compiled_filters:
        pairs = map(f, pairs)

    return [item for item, include_me in pairs if include_me]


def _compile_filter(pat: str):
    if pat.startswith("!"):
        return lambda pair: (
            (pair[0], False) if fnmatch.fnmatch(pair[0], pat[1:]) else pair
        )
    else:
        return lambda pair: ((pair[0], True) if fnmatch.fnmatch(pair[0], pat) else pair)


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


def _get_git_changes(
    *, include_unstaged: bool, since: Optional[str] = None
) -> List[Path]:
    added_paths = _git_diff_filter("A", include_unstaged=include_unstaged, since=since)
    modified_paths = _git_diff_filter(
        "M", include_unstaged=include_unstaged, since=since
    )
    return added_paths + modified_paths


def _get_git_commits(*, since: str) -> List[str]:
    # TODO: what if pushing to a different branch?
    proc = subprocess.run(
        ["git", "log", f"{since}..HEAD", "--format=%H"],
        capture_output=True,
        check=True,
        text=True,
    )
    return proc.stdout.splitlines()


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
