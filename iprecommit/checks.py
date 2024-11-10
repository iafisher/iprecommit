import fnmatch
import os
import re
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .exceptions import IPrecommitUserError


@dataclass
class Pattern:
    pattern: str
    is_include: bool

    def test(self, pair):
        if fnmatch.fnmatch(pair[0], self.pattern):
            return (pair[0], self.is_include)
        else:
            return pair


def Include(s):
    return Pattern(s, is_include=True)


def Exclude(s):
    return Pattern(s, is_include=False)


@dataclass
class CommitInfo:
    rev: str
    message: str


@dataclass
class Changes:
    added_paths: List[Path]
    modified_paths: List[Path]
    # TODO: special treatment for deleted paths?
    deleted_paths: List[Path]
    commits: Optional[List[CommitInfo]]

    def filter(self, base_pattern: Optional[str], patterns: List[Pattern]) -> "Changes":
        added_paths = _filter_paths(self.added_paths, base_pattern, patterns)
        modified_paths = _filter_paths(self.modified_paths, base_pattern, patterns)
        deleted_paths = _filter_paths(self.deleted_paths, base_pattern, patterns)
        return Changes(
            added_paths=added_paths,
            modified_paths=modified_paths,
            deleted_paths=deleted_paths,
            commits=self.commits,
        )

    def empty(self) -> bool:
        return (
            len(self.added_paths) == 0
            and len(self.modified_paths) == 0
            and (self.commits is None or len(self.commits) == 0)
            # TODO: what if a check needs to access deleted paths?
            # and len(self.deleted_paths) == 0
        )


def _filter_paths(paths, base_pattern, patterns):
    pairs = [
        (path, True if base_pattern is None else fnmatch.fnmatch(path, base_pattern))
        for path in paths
    ]

    for pattern in patterns:
        pairs = map(pattern.test, pairs)

    return [item for item, include_me in pairs if include_me]


class Base:
    # TODO: use abc.ABC?

    def check(self, changes: Changes) -> bool:
        raise NotImplementedError

    def base_pattern(self) -> Optional[str]:
        return None

    def patterns(self) -> List[Pattern]:
        return []

    # subclasses should call this at the beginning of `check` if they only work as pre-push checks
    def only_for_pre_push(self, changes: Changes) -> None:
        if changes.commits is None:
            raise IPrecommitUserError(
                f"{self.__class__.__name__} can only be used as a pre-push check."
            )


class CommitMsg:
    def check(self, text: str) -> bool:
        raise NotImplementedError


do_not_commit_pattern = re.compile(r"\bdo +not +(commit|submit)\b", flags=re.IGNORECASE)


class NoDoNotCommit(Base):
    def check(self, changes: Changes) -> bool:
        passed = True
        for path in changes.added_paths + changes.modified_paths:
            # TODO: read_text() is not safe for binary files
            if do_not_commit_pattern.search(path.read_text()) is not None:
                # TODO: should create a subclass of Path that handles this transparently
                print_path(path)
                passed = False

        return passed


do_not_push_pattern = re.compile(r"\bdo +not +(push|submit)\b", flags=re.IGNORECASE)


class NoDoNotPush(Base):
    def check(self, changes: Changes) -> bool:
        self.only_for_pre_push(changes)

        passed = True
        # `changes.commits` won't be None because of `only_for_pre_push` above, but mypy doesn't
        # know that
        commits = changes.commits or []
        for cmt in commits:
            if do_not_push_pattern.search(cmt.message) is not None:
                print(cmt.rev)
                passed = False

        return passed


class NewlineAtEndOfFile(Base):
    def check(self, changes: Changes) -> bool:
        for path in changes.added_paths + changes.modified_paths:
            # TODO: make more efficient with file seeking
            if not path.read_text().endswith("\n"):
                print_path(path)
                return False

        return True


class ShellCommandPasses(Base):
    cmd: List[str]
    pass_files: bool
    _base_pattern: Optional[str]

    def __init__(
        self, cmd, *, pass_files: bool, base_pattern: Optional[str] = None
    ) -> None:
        self.cmd = list(str(arg) for arg in cmd)
        self.pass_files = pass_files
        self._base_pattern = base_pattern

    def check(self, changes: Changes) -> bool:
        cmd = self.cmd
        if self.pass_files:
            cmd = cmd + changes.added_paths + changes.modified_paths  # type: ignore

        proc = subprocess.run(cmd)
        return proc.returncode == 0

    def base_pattern(self) -> Optional[str]:
        return self._base_pattern


class PythonFormat(Base):
    def check(self, changes: Changes) -> bool:
        proc = subprocess.run(
            ["black", "--check"] + changes.added_paths + changes.modified_paths  # type: ignore
        )
        return proc.returncode == 0

    def fix(self, changes: Changes) -> None:
        subprocess.run(["black"] + changes.added_paths + changes.modified_paths)  # type: ignore

    def base_pattern(self) -> Optional[str]:
        return "*.py"


class CommitMessageFormat(CommitMsg):
    max_length: Optional[int]
    max_first_line_length: Optional[int]
    require_capitalized: bool

    def __init__(
        self,
        *,
        max_length: Optional[int] = None,
        max_first_line_length: Optional[int] = None,
        require_capitalized: bool = False,
    ) -> None:
        super().__init__()
        self.max_length = max_length
        self.max_first_line_length = (
            max_length
            if max_first_line_length is None and max_length is not None
            else max_first_line_length
        )
        self.require_capitalized = require_capitalized

    def check(self, text: str) -> bool:
        if not text:
            print("commit message is empty")
            return False

        passed = True
        first_line, *lines = text.splitlines()

        if not first_line:
            print("first line should not be blank")
            passed = False

        if first_line and first_line[0].isspace():
            print("first line should not start with whitespace")
            passed = False

        if len(lines) > 0 and lines[0] != "":
            print("should be a blank line after first line")
            passed = False

        if self.max_first_line_length is not None:
            line_ok = self._check_line(1, first_line, self.max_first_line_length)
            if not line_ok:
                passed = False

        if self.max_length is not None:
            for lineno, line in enumerate(lines, start=2):
                line_ok = self._check_line(lineno, line, self.max_length)
                if not line_ok:
                    passed = False

        if self.require_capitalized and (first_line and first_line[0].islower()):
            print("first line should be capitalized")
            passed = False

        return passed

    def _check_line(self, lineno: int, line: str, max_length: int) -> bool:
        if len(line) > max_length:
            trunc = textwrap.shorten(line, width=15, placeholder="...")
            print(f"line {lineno} too long: len={len(line)}, max={max_length}: {trunc}")
            return False
        else:
            return True


def print_path(p: Path) -> None:
    try:
        print(p)
    except UnicodeEncodeError:
        print(os.fsencode(p))
