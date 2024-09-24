import abc
import ast
import atexit
import fnmatch
import os
import shlex
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


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

    def as_list(self, *, include_deleted: bool = True) -> List[Path]:
        if include_deleted:
            return self.added_files + self.modified_files + self.deleted_files
        else:
            return self.added_files + self.modified_files


def _apply_filter(
    files: List[Path], pattern_list: List[str], exclude_list: List[str]
) -> List[Path]:
    r = [
        f
        for f in files
        if not pattern_list or any(fnmatch.fnmatch(str(f), p) for p in pattern_list)
    ]
    r = [
        f
        for f in r
        if not exclude_list or all(not fnmatch.fnmatch(str(f), p) for p in exclude_list)
    ]
    return r


@dataclass
class Message:
    message: str
    path: Optional[Path]


class BaseCheck(abc.ABC):
    @abc.abstractmethod
    def check(self, changes: Changes) -> List[Message]:
        pass

    def fix(self, changes: Changes) -> List[Message]:
        return []

    # returns (pattern, exclude)
    def get_intrinsic_filters(self) -> Tuple[List[str], List[str]]:
        return ([], [])


class BaseCommand(BaseCheck):
    def __init__(
        self,
        args,
        *,
        pass_files: bool = False,
        separately: bool = False,
        include_deleted: bool = False,
        invert_returncode: bool = False,
    ) -> None:
        if separately and not pass_files:
            raise IPrecommitConfigError("separately=True requires pass_files=True")

        if include_deleted and not pass_files:
            raise IPrecommitConfigError("include_deleted=True requires pass_files=True")

        self.args = list(args)
        self.pass_files = pass_files
        self.separately = separately
        self.include_deleted = include_deleted
        self.invert_returncode = invert_returncode

    def check(self, changes: Changes) -> List[Message]:
        args = self.args[:]
        if self.pass_files:
            if self.separately:
                list_of_arglists = []
                for changed_file in changes.as_list(
                    include_deleted=self.include_deleted
                ):
                    list_of_arglists.append(list(args) + [changed_file])
            else:
                args.extend(changes.as_list())
                list_of_arglists = [args]
        else:
            list_of_arglists = [args]

        messages = []
        for arglist in list_of_arglists:
            result = subprocess.run(
                arglist, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )
            if self.invert_returncode:
                failed = result.returncode == 0
            else:
                failed = result.returncode != 0

            if failed:
                messages.append(Message(result.stdout, None))

        return messages


class Precommit:
    def __init__(self) -> None:
        env_config = get_environment_config()

        self.fancy_output = env_config.fancy_output
        self.in_fix_mode = env_config.fix
        self.changes = _get_changes(include_unstaged=env_config.unstaged)
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

        checker_pattern, checker_exclude = checker.get_intrinsic_filters()
        pattern += checker_pattern
        exclude += checker_exclude

        changes = self.changes.filtered(pattern, exclude=exclude)
        if changes.is_empty():
            self.print_skipped(label)
            return

        if self.in_fix_mode:
            self._fix(checker, changes, label=label)
            return

        self.print_running(label)
        try:
            messages = checker.check(changes)
        except Exception as e:
            if self.fancy_output:
                print()
            raise e

        if self.fancy_output:
            # clear to beginning of line
            print("\033[1K", end="")
            # return cursor to beginning of line
            print("\r", end="")
            sys.stdout.flush()

        if len(messages) > 0:
            self.num_failed_checks += 1
            self.print_failure(label, "\n".join(m.message for m in messages))
        else:
            self.print_success(label)

    def _fix(self, checker: BaseCheck, changes: Changes, *, label: str) -> None:
        messages = checker.fix(changes)
        for m in messages:
            self.print_fix(label, m.path)

    def command(
        self,
        args: List[str],
        *,
        pass_files: bool = False,
        separately: bool = False,
        invert_returncode: bool = False,
        pattern: List[str] = [],
        exclude: List[str] = [],
        label: str = "",
    ) -> None:
        if not label:
            label = "Command: " + " ".join(shlex.quote(str(a)) for a in args)

        return self.check(
            BaseCommand(
                args,
                pass_files=pass_files,
                separately=separately,
                invert_returncode=invert_returncode,
            ),
            pattern=pattern,
            exclude=exclude,
            label=label,
        )

    def print_running(self, label: str) -> None:
        if self.fancy_output:
            print(f"{cyan('running:')} {label}", end="")
            sys.stdout.flush()

    def print_failure(self, label: str, message: str) -> None:
        print(f"{red('failed:')} {label}")
        if message:
            print(textwrap.indent(message, "  "))
            print()

    def print_success(self, label: str) -> None:
        print(f"{green('passed:')} {label}")

    def print_skipped(self, label: str) -> None:
        print(f"{yellow('skipped:')} {label}")

    def print_fix(self, label: str, path: Optional[Path]) -> None:
        print(f"{cyan('fixed:')} {label}: {path}")

    def atexit(self):
        if self.num_failed_checks > 0:
            msg = red(f"{self.num_failed_checks} failed")
            print()
            print(f"{msg}. Commit aborted.")
            os._exit(1)


@dataclass
class EnvironmentConfig:
    # run on unstaged as well as staged files
    unstaged: bool
    # run in 'fix' mode instead of 'check' mode
    fix: bool
    # enable fancy output (disabled in functional test so that output can be more easily diffed)
    fancy_output: bool


def get_environment_config() -> EnvironmentConfig:
    return EnvironmentConfig(
        unstaged=get_binary_envvar_or_warn("IPRECOMMIT_UNSTAGED"),
        fix=get_binary_envvar_or_warn("IPRECOMMIT_FIX"),
        fancy_output=get_binary_envvar_or_warn("IPRECOMMIT_FANCY_OUTPUT", default=True),
    )


def get_binary_envvar_or_warn(name: str, *, default=False) -> bool:
    envvar = os.environ.get(name)
    if envvar is None:
        return default
    elif envvar == "0":
        return False
    elif envvar == "1":
        return True
    else:
        warn(f"{name} is defined but ignored because its value is not '1' or '0'.")
        return default


def warn(msg: str) -> None:
    print(f"{yellow('Warning:')} {msg}")


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


class IPrecommitError(Exception):
    pass


class IPrecommitConfigError(Exception):
    pass