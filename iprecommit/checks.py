import fnmatch
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


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
class Changes:
    added_paths: List[Path]
    modified_paths: List[Path]
    # TODO: special treatment for deleted paths?
    deleted_paths: List[Path]

    def filter(self, base_pattern: Optional[str], patterns: List[Pattern]) -> "Changes":
        added_paths = _filter_paths(self.added_paths, base_pattern, patterns)
        modified_paths = _filter_paths(self.modified_paths, base_pattern, patterns)
        deleted_paths = _filter_paths(self.deleted_paths, base_pattern, patterns)
        return Changes(
            added_paths=added_paths,
            modified_paths=modified_paths,
            deleted_paths=deleted_paths,
        )

    def empty(self) -> bool:
        return (
            len(self.added_paths) == 0
            and len(self.modified_paths) == 0
            and len(self.deleted_paths) == 0
        )


def _filter_paths(paths, base_pattern, patterns):
    pairs = [
        (path, True if base_pattern is None else fnmatch.fnmatch(path, base_pattern))
        for path in paths
    ]

    for pattern in patterns:
        pairs = map(pattern.test, pairs)

    return [item for item, include_me in pairs if include_me]


@dataclass
class Settings:
    base_pattern: Optional[str]
    patterns: List[Pattern]


class Base:
    # TODO: use abc.ABC?

    def check(self, changes: Changes) -> bool:
        raise NotImplementedError

    def name(self) -> str:
        return self.__class__.__name__
    
    def base_pattern(self) -> Optional[str]:
        return None
    
    def patterns(self) -> List[Pattern]:
        return []


class NoDoNotSubmit(Base):
    def check(self, changes: Changes) -> bool:
        for path in changes.added_paths + changes.modified_paths:
            # TODO: report bad path
            if "DO NOT SUBMIT" in path.read_text():
                return False

        return True


class NewlineAtEndOfFile(Base):
    def check(self, changes: Changes) -> bool:
        for path in changes.added_paths + changes.modified_paths:
            # TODO: report bad path
            # TODO: make more efficient with file seeking
            if not path.read_text().endswith("\n"):
                return False

        return True
    

class ShellCommandPasses(Base):
    cmd: List[str]
    pass_files: bool
    _base_pattern: Optional[str]

    def __init__(self, cmd, *, pass_files: bool, base_pattern: Optional[str] = None) -> None:
        self.cmd = list(str(arg) for arg in cmd)
        self.pass_files = pass_files
        self._base_pattern = base_pattern

    def check(self, changes: Changes) -> bool:
        cmd = self.cmd
        if self.pass_files:
            cmd = cmd + changes.added_paths + changes.modified_paths

        proc = subprocess.run(cmd)
        return proc.returncode == 0
    
    def name(self):
        return " ".join(map(shlex.quote, self.cmd))

    def base_pattern(self) -> Optional[str]:
        return self._base_pattern


class PythonFormat(Base):
    def check(self, changes: Changes) -> bool:
        proc = subprocess.run(
            ["black", "--check"] + changes.added_paths + changes.modified_paths
        )
        return proc.returncode == 0

    def fix(self, changes: Changes) -> None:
        subprocess.run(["black"] + changes.added_paths + changes.modified_paths)

    def base_pattern(self) -> Optional[str]:
        return "*.py"
