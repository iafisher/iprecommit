import abc
import ast
import atexit
import argparse
import importlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List


DEFAULT_HOOK_PATH = "hooks/precommit.py"


def main():
    argparser = argparse.ArgumentParser(
        prog="iprecommit", description="Manage Git pre-commit hooks."
    )

    version = importlib.metadata.version("iprecommit")
    argparser.add_argument("--version", action="version", version=version)

    subparsers = argparser.add_subparsers(metavar="subcommand")

    argparser_fix = subparsers.add_parser("fix", help="Fix pre-commit failures.")
    argparser_fix.add_argument(
        "--unstaged", action="store_true", help="Fix failures in unstaged changes, too."
    )
    argparser_fix.set_defaults(func=main_fix)

    argparser_init = subparsers.add_parser(
        "init", help="Initialize a new pre-commit hook."
    )
    argparser_init.add_argument(
        "--hook", default=DEFAULT_HOOK_PATH, help="Where to create the hook script"
    )
    argparser_init.add_argument(
        "--force", action="store_true", help="Overwrite existing files."
    )
    argparser_init.set_defaults(func=main_init)

    argparser_run = subparsers.add_parser(
        "run", help="Run the pre-commit checks manually."
    )
    argparser_run.add_argument(
        "--unstaged", action="store_true", help="Fix failures in unstaged changes, too."
    )
    argparser_run.set_defaults(func=main_run)

    argparser_uninstall = subparsers.add_parser(
        "uninstall", help="Uninstall the pre-commit hook from the Git repository."
    )
    argparser_uninstall.set_defaults(func=main_uninstall)

    args = argparser.parse_args()
    # TODO: handle case where `args.func` is missing
    args.func(args)


PRECOMMIT_TEMPLATE = """\
from iprecommit import Precommit, checks

pre = Precommit()
pre.check(checks.NoDoNotSubmit())
pre.check(checks.NewlineAtEndOfFile())
# run a command:
#   pre.sh("./run_tests", "--verbose")
#   pre.sh("black", "--check", pass_files=True, pattern="*.py")
"""


class Reporter(abc.ABC):
    failed: bool

    @abc.abstractmethod
    def fail(self, message: str) -> None:
        pass

    @abc.abstractmethod
    def log(self, message: str) -> None:
        pass

    @abc.abstractmethod
    def verbose(self, message: str) -> None:
        pass


class ProductionReporter(Reporter):
    failed: bool

    def fail(self, message: str) -> None:
        raise NotImplementedError

    def log(self, message: str) -> None:
        raise NotImplementedError

    def verbose(self, message: str) -> None:
        raise NotImplementedError


@dataclass
class Changes:
    added_paths: List[Path]
    modified_paths: List[Path]
    deleted_paths: List[Path]


class BaseChecker(abc.ABC):
    # TODO: what do abc.ABC and abstractmethod actually do?
    @abc.abstractmethod
    def check(self, reporter: Reporter, changes: Changes) -> None:
        pass

    # TODO: how to report 'intrinsic' include/exclude?
    # TODO: how to report whether fixable or not?


class BasePerFileChecker(BaseChecker):
    def check(self, reporter: Reporter, changes: Changes) -> None:
        for path in changes.added_paths + changes.modified_paths:
            self.check_one_file(reporter, path)

    def check_one_file(self, reporter: Reporter, path: Path) -> None:
        raise NotImplementedError


class NoDoNotSubmitChecker(BasePerFileChecker):
    def check_one_file(self, reporter: Reporter, path: Path) -> None:
        if "DO NOT SUBMIT" in path.read_text():
            # TODO: line number
            reporter.fail(f"'DO NOT SUBMIT' found in {path}")


class Precommit:
    fix_mode: bool
    unstaged: bool

    def __init__(self):
        self._parse_cmdline_args()
        atexit.register(self._atexit)

        changes = _get_git_changes()
        self.internal = PrecommitInternal(changes)

    def check(self, checker: BaseChecker) -> None:
        if self.fix_mode:
            self.internal.fix(checker)
        else:
            self.internal.check(checker)

    def _parse_cmdline_args(self):
        raise NotImplementedError

    def _atexit(self) -> None:
        if self.internal.num_failed_checks > 0:
            msg = red(f"{self.internal.num_failed_checks} failed")
            print()
            print(f"{msg}. Commit aborted.")
            # use _exit() to avoid recursively invoking ourselves as an atexit hook
            os._exit(1)


class PrecommitInternal:
    # Precommit is for end users and does some magical stuff, like parsing command-line arguments
    # and registering an atexit hook.
    #
    # PrecommitInternal is the core functionality, in a class that's easy to test.

    changes: Changes
    num_failed_checks: int

    def __init__(self, changes: Changes, *, reporter_factory) -> None:
        self.changes = changes
        self.num_failed_checks = 0
        self.reporter_factory = reporter_factory

    def fix(self, checker: BaseChecker) -> None:
        raise NotImplementedError

    def check(self, checker: BaseChecker) -> None:
        reporter = self.reporter_factory()
        # TODO: handle include/exclude
        checker.check(reporter, self.changes)
        if reporter.failed:
            self.num_failed_checks += 1


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


def main_init(args):
    create_precommit_py()
    install_git_hook()


def create_precommit_py():
    raise NotImplementedError


def install_git_hook():
    raise NotImplementedError


def main_run(args):
    invoke_precommit_py(raw_args)


def main_fix(args):
    invoke_precommit_py(raw_args)


def invoke_precommit_py(raw_args):
    hook_path = find_hook_path()
    # TODO: less hacky way to do this?
    # TODO: what if sys.executable is None?
    proc = subprocess.run([sys.executable, hook_path] + raw_args)
    sys.exit(proc.returncode)


def find_hook_path() -> Path:
    raise NotImplementedError


def main_uninstall(args):
    uninstall_git_hook()


def uninstall_git_hook():
    raise NotImplementedError
