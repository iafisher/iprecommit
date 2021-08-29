"""
The main library for the precommit tool.

Holds the machinery for running pre-commit checks and fixes and reporting the results.
The checks themselves are defined in checks.py.

Author:  Ian Fisher (iafisher@fastmail.com)
Version: May 2020
"""
import ast
import fnmatch
import subprocess
import sys
import time
from collections import namedtuple
from typing import List, Optional, Union

from . import utils


class Precommit:
    def __init__(
        self, checks: List["BaseCheck"], *, check_all: bool, working: bool
    ) -> None:
        """
        Parameters:
          checks: The list of checks to run.
          check_all: Whether to run all checks, including slow ones.
          working: Whether to check the working directory as well as staged files.
        """
        # Calling it `self._checks` instead of `self.checks` avoids giving a confusing
        # error message for the common typo of `precommit.checks(...)` instead of
        # `precommit.check(...)`.
        self._checks = checks
        self.check_all = check_all
        self.working = working

        self.num_of_checks = 0
        self.num_of_skipped_checks = 0
        self.num_of_problems = 0
        self.num_of_fixable_problems = 0

    def check(self) -> bool:
        """
        Finds problems and print a message for each.

        Returns True if any problems were found.
        """
        if not self._checks:
            print("No checks were registered.")
            return False

        self.start = time.monotonic()
        repository = self.get_repository()
        files = (
            repository.unstaged + repository.staged
            if self.working
            else repository.staged
        )
        deleted_files = (
            repository.unstaged_deleted + repository.staged_deleted
            if self.working
            else repository.staged_deleted
        )
        if not (files or deleted_files):
            print("No files to check.")
            return False

        for check in self._checks:
            if not self.should_run(check):
                self.num_of_skipped_checks += 1
                if utils.VERBOSE:
                    self.print_check_header_and_status(check, "skipped")
                continue

            if not check.filter(files):
                if utils.VERBOSE:
                    self.print_check_header_and_status(check, "skipped")
                continue

            self.pre_check(check)
            problem = check.check(check.filter(files), stream_output=True)
            status = utils.red("failed!") if problem else utils.green("passed!")
            self.post_check(check, status, problem)

        self.print_summary_for_check()
        return self.num_of_problems > 0

    def fix(self) -> None:
        """Finds problems and fixes the ones that can be fixed automatically."""
        if not self._checks:
            print("No checks were registered.")
            return

        self.start = time.monotonic()
        repository = self.get_repository()
        files = (
            repository.unstaged + repository.staged
            if self.working
            else repository.staged
        )
        deleted_files = (
            repository.unstaged_deleted + repository.staged_deleted
            if self.working
            else repository.staged_deleted
        )
        if not (files or deleted_files):
            print("No files to fix.")

        for check in self._checks:
            if not check.is_fixable():
                continue

            if not self.should_run(check):
                self.num_of_skipped_checks += 1
                if utils.VERBOSE:
                    self.print_check_header_and_status(check, "skipped")
                continue

            if not check.filter(files):
                if utils.VERBOSE:
                    self.print_check_header_and_status(check, "skipped")
                continue

            self.pre_check(check)
            problem = check.check(check.filter(files), stream_output=False)

            if problem and problem.autofix:
                run(problem.autofix, stream_output=True)

            status = utils.green("fixed!") if problem else utils.green("passed!")
            self.post_check(check, status, problem)

        run(["git", "add"] + files, stream_output=False)
        self.print_summary_for_fix()

    def print_summary_for_check(self) -> None:
        print()
        print("Ran", utils.blue(utils.plural(self.num_of_checks, "check")), end=". ")
        if self.num_of_problems > 0:
            print(
                f"Detected {utils.red(utils.plural(self.num_of_problems, 'issue'))}",
                end=". ",
            )

            if self.num_of_fixable_problems > 0:
                if self.num_of_fixable_problems == self.num_of_problems:
                    n = utils.green("all of them")
                else:
                    n = utils.blue(f"{self.num_of_fixable_problems} of them")

                print(f"Fix {n} with `{utils.blue('precommit fix')}`.", end="")

            print()
        else:
            print(f"{utils.green('No issues')} detected.")

        if self.num_of_skipped_checks > 0:
            n = utils.yellow(utils.plural(self.num_of_skipped_checks, "check"))
            print(f"Skipped {n}", end=". ")
            print(f"Run all checks with `{utils.blue('precommit --all')}`.")

    def print_summary_for_fix(self) -> None:
        print()
        print(
            "Ran",
            utils.blue(utils.plural(self.num_of_checks, "fixable check")),
            end=". ",
        )
        print(
            "Detected", utils.red(utils.plural(self.num_of_problems, "issue")), end=". "
        )
        print("Fixed " + utils.green(f"{self.num_of_fixable_problems} of them") + ".")

    def pre_check(self, check: "BaseCheck") -> None:
        if utils.VERBOSE:
            print(f"Running {check.get_name()}")
            self.check_start = time.monotonic()

        self.num_of_checks += 1
        self.print_check_header(check)

    def post_check(
        self, check: "BaseCheck", status: str, problem: Optional["Problem"]
    ) -> None:
        if problem is not None:
            self.num_of_problems += 1
            if check.is_fixable():
                self.num_of_fixable_problems += 1

        self.print_check_status(status)

        if utils.VERBOSE:
            self.check_end = time.monotonic()
            elapsed = self.check_end - self.check_start
            elapsed_since_start = self.check_end - self.start
            print(f"Finished in {elapsed:.2f}s. ", end="")
            print(f"{elapsed_since_start:.2f}s since start.")

        print()

    def print_check_header_and_status(self, check: "BaseCheck", status: str) -> None:
        self.print_check_header(check)
        self.print_check_status(status)
        print()

    def print_check_header(self, check: "BaseCheck") -> None:
        print(utils.blue("o--[ " + check.get_name() + " ]"))

    def print_check_status(self, status: str) -> None:
        print(utils.blue("o--[ ") + status + utils.blue(" ]"))

    def should_run(self, check: "BaseCheck") -> bool:
        return not check.slow or self.check_all

    def get_repository(self) -> "Repository":
        staged = get_staged_files()
        staged_deleted = get_staged_deleted_files()
        unstaged = get_unstaged_files()
        unstaged_deleted = get_unstaged_deleted_files()
        return Repository(
            staged=staged,
            staged_deleted=staged_deleted,
            unstaged=unstaged,
            unstaged_deleted=unstaged_deleted,
        )


class Checklist:
    def __init__(self) -> None:
        self._checks: List["BaseCheck"] = []

    def check(self, check: "BaseCheck") -> None:
        """Registers the pre-commit check."""
        if not isinstance(check, BaseCheck):
            raise UsageError("check must be a subclass of BaseCheck")

        self._checks.append(check)


class BaseCheck:
    def __init__(
        self, slow: bool = False, include: List[str] = [], exclude: List[str] = []
    ) -> None:
        """
        Parameters:
          slow: Whether the check is slow and should not be run by default.
          include: A list of patterns for file paths that the check should run on. If
            left as the empty list, then the check runs on all files.
          exclude: A list of patterns for file paths that the check should NOT run on.
            Takes precedence over `include`, i.e. if a file path matches a pattern in
            `include` and in `exclude`, the file path will be excluded.
        """
        if isinstance(include, str):
            raise UsageError("include should be a list of strings")

        if isinstance(exclude, str):
            raise UsageError("exclude should be a list of strings")

        self.slow = slow
        self.include = include if include is not None else []
        self.exclude = exclude if exclude is not None else []

    def check(self, files: List[str], *, stream_output: bool) -> Optional["Problem"]:
        raise NotImplementedError

    def get_name(self) -> str:
        return self.__class__.__name__

    def is_fixable(self) -> bool:
        return False

    def filter(self, paths: List[str]) -> List[str]:
        if self.include:
            filtered = [
                p
                for p in paths
                if any(fnmatch.fnmatch(p, pattern) for pattern in self.include)
            ]
        else:
            filtered = paths

        if self.exclude:
            filtered = [
                p
                for p in filtered
                if not any(fnmatch.fnmatch(p, pattern) for pattern in self.exclude)
            ]

        return filtered


def decode_git_path(path: str) -> str:
    """
    Converts a path string as Git displays it to a UTF-8 encoded string.

    If the file path contains a non-ASCII character or a literal double quote, Git
    backslash-escapes the offending character and encloses the whole path in double
    quotes. This function reverses that transformation and decodes the resulting bytes
    as UTF-8.
    """
    if path.startswith('"') and path.endswith('"'):
        # TODO(2020-04-16): Do I need to add "b" and then decode, or can I just eval?
        return ast.literal_eval("b" + path).decode("utf-8")
    else:
        return path


class Problem:
    def __init__(
        self, autofix: Optional[List[str]] = None, message: str = None
    ) -> None:
        self.autofix = autofix
        self.message = message


def get_staged_files() -> List[str]:
    return _read_files_from_git(["--cached", "--diff-filter=d"])


def get_staged_deleted_files() -> List[str]:
    return _read_files_from_git(["--cached", "--diff-filter=D"])


def get_unstaged_files() -> List[str]:
    return _read_files_from_git(["--diff-filter=d"])


def get_unstaged_deleted_files() -> List[str]:
    return _read_files_from_git(["--diff-filter=D"])


def _read_files_from_git(args: List[str]) -> List[str]:
    result = run(["git", "diff", "--name-only"] + args, stream_output=False)
    return [decode_git_path(p) for p in result.stdout.decode("ascii").splitlines()]


CommandResult = namedtuple("CommandResult", ["returncode", "stdout"])


def run(
    cmd: Union[List[str], str],
    *,
    shell: bool = False,
    stream_output: bool,
    working_directory: str = None,
) -> CommandResult:
    """
    Runs a shell command.

    If `stream_output` is True, then the output is streamed to the console rather than
    captured and suppressed.

    Due to inconsistencies with the Python subprocess API, this function returns an
    object of type `CommandResult`.
    """
    if utils.VERBOSE:
        cmd_as_string = " ".join(cmd) if isinstance(cmd, list) else cmd
        print("Running command: " + cmd_as_string)

    if not stream_output:
        r = subprocess.run(
            cmd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        return CommandResult(returncode=r.returncode, stdout=r.stdout)
    else:
        # Normally this isn't necessary, but sometimes when you pipe precommit
        # itself to another command or to a file (as the functional test does), then
        # it will print all the output of the command below before any of
        # precommit's output, for reasons that remain obscure to me.
        sys.stdout.flush()

        # Print the prefix before each line of the command's output by piping it to
        # sed.
        ps = subprocess.Popen(
            cmd,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=working_directory,
        )
        subprocess.run(
            ["sed", "-e", "s/^/" + utils.blue("|  ") + "/"],
            stdin=ps.stdout,
            stderr=subprocess.STDOUT,
        )
        returncode = ps.wait()
        return CommandResult(returncode=returncode, stdout=None)


class Repository:
    def __init__(
        self,
        staged: List[str],
        staged_deleted: List[str],
        unstaged: List[str],
        unstaged_deleted: List[str],
    ) -> None:
        self.staged = staged
        self.staged_deleted = staged_deleted
        self.unstaged = unstaged
        self.unstaged_deleted = unstaged_deleted


class UsageError(Exception):
    """Exception for incorrect usage of the precommit API."""
