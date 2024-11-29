import contextlib
import fnmatch
import os
import shlex
import subprocess
import sys
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, NoReturn, Optional, Tuple, Union

from . import toml


@dataclass
class PreCommitCheck:
    name: Optional[str]
    cmd: List[str]
    fix_cmd: List[str]
    pass_files: bool
    filters: List[str]
    working_dir: Optional[str]


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


@dataclass
class Config:
    pre_commit_checks: List[PreCommitCheck]
    pre_push_checks: List[PrePushCheck]
    commit_msg_checks: List[CommitMsgCheck]


def parse_config_toml(path: Path) -> Config:
    raw_toml = toml.load(path, OrderedDict)

    # TODO: tests for TOML parsing and error messages
    pre_commit_toml_list = raw_toml.pop("pre_commit", [])
    commit_msg_toml_list = raw_toml.pop("commit_msg", [])
    pre_push_toml_list = raw_toml.pop("pre_push", [])
    ensure_dict_empty(raw_toml, "The top-level table")

    if not isinstance(pre_commit_toml_list, list) or any(
        not isinstance(d, dict) for d in pre_commit_toml_list
    ):
        raise IPrecommitTomlError(
            "'pre_commit' in your TOML file should be an array of tables (e.g., [[pre_commit]])."
        )

    if not isinstance(commit_msg_toml_list, list) or any(
        not isinstance(d, dict) for d in commit_msg_toml_list
    ):
        raise IPrecommitTomlError(
            "'commit_msg' in your TOML file should be an array of tables (e.g., [[commit_msg]])."
        )

    if not isinstance(pre_push_toml_list, list) or any(
        not isinstance(d, dict) for d in pre_push_toml_list
    ):
        raise IPrecommitTomlError(
            "'pre_push' in your TOML file should be an array of tables (e.g., [[pre_push]])."
        )

    config = Config(pre_commit_checks=[], pre_push_checks=[], commit_msg_checks=[])

    for pre_commit_toml in pre_commit_toml_list:
        table_name = "[[pre_commit]]"
        name = validate_optional_string_key(pre_commit_toml, "name", table_name)
        cmd = validate_cmd_key(pre_commit_toml, table_name)
        fix_cmd = validate_cmd_key(
            pre_commit_toml, table_name, key="fix_cmd", default=[]
        )
        filters = validate_cmd_key(
            pre_commit_toml, table_name, key="filters", default=[]
        )
        working_dir = validate_optional_string_key(
            pre_commit_toml, "working_dir", table_name
        )

        pass_files = pre_commit_toml.pop("pass_files", True)
        if not isinstance(pass_files, bool):
            raise IPrecommitTomlError(
                "The 'pass_files' key of [[pre_commit]] entries in your TOML file should be a boolean."
            )

        ensure_dict_empty(pre_commit_toml, "A [[pre_commit]] entry")
        config.pre_commit_checks.append(
            PreCommitCheck(
                name=name,
                cmd=cmd,
                fix_cmd=fix_cmd,
                pass_files=pass_files,
                filters=filters,
                working_dir=working_dir,
            )
        )

    for commit_msg_toml in commit_msg_toml_list:
        table_name = "[[commit_msg]]"
        name = validate_optional_string_key(commit_msg_toml, "name", table_name)
        cmd = validate_cmd_key(commit_msg_toml, table_name)

        ensure_dict_empty(commit_msg_toml, "A [[commit_msg]] entry")
        config.commit_msg_checks.append(CommitMsgCheck(name=name, cmd=cmd))

    for pre_push_toml in pre_push_toml_list:
        table_name = "[[pre_push]]"
        name = validate_optional_string_key(pre_push_toml, "name", table_name)
        cmd = validate_cmd_key(pre_push_toml, table_name)

        ensure_dict_empty(pre_push_toml, f"A {table_name} entry")
        config.pre_push_checks.append(PrePushCheck(name=name, cmd=cmd))

    return config


def validate_optional_string_key(table, key, table_name):
    v = table.pop(key, None)
    if v is not None and not isinstance(v, str):
        raise IPrecommitTomlError(
            f"The '{key}' key of {table_name} entries in your TOML file should be a string."
        )

    return v


_Unset = object()


def validate_cmd_key(table, table_name, key="cmd", default=_Unset):
    if default is not _Unset:
        v = table.pop(key, default)
    else:
        try:
            v = table.pop(key)
        except KeyError:
            raise IPrecommitTomlError(
                f"A {table_name} table in your TOML file is missing a '{key}' key."
            )

    if not isinstance(v, list) or any(not isinstance(a, str) for a in v):
        raise IPrecommitTomlError(
            "The '{key}' key of {table_name} entries in your TOML file should be a list of strings."
        )

    return v


def ensure_dict_empty(d, name):
    try:
        key = next(iter(d.keys()))
    except StopIteration:
        pass
    else:
        raise IPrecommitTomlError(
            f"{name} in your TOML file has a key that iprecommit does not recognize: {key}"
        )


class Checks:
    num_failed_checks: int
    config: Config

    def __init__(self, config: Config) -> None:
        self.num_failed_checks = 0
        self.config = config

    def run_pre_commit(
        self, *, fix_mode: bool, unstaged: bool, all_files: bool
    ) -> None:
        assert not (unstaged and all_files)

        if all_files:
            all_changed_paths = list(
                sorted(
                    set(_get_all_git_files() + _get_git_changes(include_unstaged=True))
                )
            )
        else:
            all_changed_paths = _get_git_changes(include_unstaged=unstaged)

        for check in self.config.pre_commit_checks:
            name = get_check_name(check)

            filtered_changed_paths = _filter_paths(all_changed_paths, check.filters)
            if not filtered_changed_paths:
                self._print_status(name, yellow("skipped"))
                continue

            if fix_mode:
                if check.fix_cmd:
                    self._print_status(name, "fixing")
                    cmd = check.fix_cmd
                    if check.pass_files:
                        cmd += filtered_changed_paths  # type: ignore
                    success = self._run_one(cmd, working_dir=check.working_dir)
                    if not success:
                        # TODO: test for fix failed
                        self._print_status(name, red("fix failed"))
                    else:
                        self._print_status(name, "finished")
                        if not unstaged:
                            proc = subprocess.run(["git", "add"] + filtered_changed_paths)  # type: ignore
                            if proc.returncode != 0:
                                self._print_status(
                                    name,
                                    yellow("staging fixed files with 'git add' failed"),
                                )
                else:
                    continue
            else:
                self._print_status(name, "running")
                cmd = check.cmd
                # TODO: test where pass_files=False
                if check.pass_files:
                    cmd += filtered_changed_paths  # type: ignore
                success = self._run_one(cmd, working_dir=check.working_dir)
                if not success:
                    self._print_status(name, red("failed"))
                    self.num_failed_checks += 1
                else:
                    self._print_status(name, green("passed"))
            print()
            print()

        self._summary("Commit")

    def run_commit_msg(self, commit_msg_file: Path) -> None:
        print()
        print()
        print("== checking commit message ==")
        print()
        print()

        for check in self.config.commit_msg_checks:
            name = get_check_name(check)

            self._print_status(name, "running")
            success = self._run_one(check.cmd + [commit_msg_file])
            if not success:
                self._print_status(name, red("failed"))
                self.num_failed_checks += 1
            else:
                self._print_status(name, green("passed"))

            print()
            print()

        self._summary("Commit")

    def run_pre_push(self, remote: str) -> None:
        current_branch = _get_git_current_branch()
        last_commit_pushed = _get_git_last_commit_pushed(remote, current_branch)
        commits = _get_git_commits(since=last_commit_pushed)

        for check in self.config.pre_push_checks:
            name = get_check_name(check)

            self._print_status(name, "running")
            success = self._run_one(check.cmd + commits)
            if not success:
                self._print_status(name, red("failed"))
                self.num_failed_checks += 1
            else:
                self._print_status(name, green("passed"))

            print()
            print()

        self._summary("Push")

    def _run_one(self, cmd, *, working_dir=None) -> bool:
        # stderr of check commands is really part of normal output, so pipe it to stdout
        # also makes it easier to assert on intermingled stdout/stderr in tests
        do_it = lambda: subprocess.run(cmd, stderr=subprocess.STDOUT)

        if working_dir is not None:
            with contextlib.chdir(working_dir):
                proc = do_it()
        else:
            proc = do_it()

        return proc.returncode == 0

    def _summary(self, action: str) -> None:
        if self.num_failed_checks > 0:
            s = f"{self.num_failed_checks} failed"
            print(f"{red(s)}. {action} aborted.")
            sys.stdout.flush()
            sys.exit(1)

    def _print_status(self, name: str, status: str) -> None:
        print(f"{cyan('[iprecommit]')} {name}: {status}")
        sys.stdout.flush()


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


def _get_all_git_files() -> List[Path]:
    proc = subprocess.run(
        ["git", "ls-tree", "-r", "HEAD", "--name-only", "-z"],
        capture_output=True,
        check=True,
    )
    return [Path(os.fsdecode(p)) for p in proc.stdout.split(b"\x00") if p]


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


class IPrecommitTomlError(IPrecommitError):
    pass
