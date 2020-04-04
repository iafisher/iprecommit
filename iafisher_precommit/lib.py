import ast
import re
import subprocess
import sys
import textwrap
import time
from collections import namedtuple


class Precommit:
    def __init__(self, *, encoding="utf-8"):
        self.encoding = encoding
        self.checks = []
        self.verbose = False
        self.check_all = False
        # Cached result of self.get_repository()
        self._repository = None

    def set_args(self, args):
        if "--verbose" in args.flags:
            self.verbose = args.flags["--verbose"]

        if "--all" in args.flags:
            self.check_all = args.flags["--all"]

    def register(self, check, *, pattern=None, slow=False, fatal=False):
        """Registers the pre-commit check.

        Args:
          check: The check object itself.
          pattern: A regular expression pattern, as a string. If not None, then the
            check will only run on file paths which match this pattern. This argument
            is only valid if check is a subclass of FileCheck, since RepoCheck checks
            don't run on individual files.
          slow: Whether the check is expected to be slow or not. If True, then the check
            will not be invoked unless the precommit command is invoked with the --all
            flag. By default, the pre-commit hook that is installed in git uses the
            --all flag.
          fatal: Whether a check failure should immediately end the pre-commit check.
        """
        check.slow = slow
        check.fatal = fatal
        if isinstance(check, FileCheck):
            if check.pattern is None and pattern is not None:
                check.pattern = pattern
        elif isinstance(check, RepoCheck):
            if pattern is not None:
                raise UsageError("cannot use pattern with RepoCheck")
        else:
            raise UsageError("check must be a subclass of FileCheck or RepoCheck")

        self.checks.append(check)

    def check(self):
        """Find problems and print a message for each."""
        start = time.monotonic()
        checks_to_run = self.get_checks()
        problems = []
        for check, arg in checks_to_run:
            print(blue("[" + check.name() + "] "), end="", flush=True)
            new_problems = self.run_check(check, start, args=(arg,))
            problems.extend(new_problems)
            if new_problems:
                for problem in new_problems:
                    print_problem(problem)
            else:
                print("no issues")

        if problems:
            fixable_problems = [problem for problem in problems if problem.autofix]
            print()
            print(f"{red(plural(len(problems), 'issue'))} found. ", end="")
            if fixable_problems:
                if len(fixable_problems) == len(problems):
                    n = green("all of them")
                else:
                    n = blue(f"{len(fixable_problems)} of them")

                print(f"Fix {n} with '{blue('precommit fix')}'.", end="")
            print()
            sys.exit(1)
        else:
            print(f"{green('No issues')} detected.")

    def fix(self, *, dry_run=False):
        start = time.monotonic()
        checks_to_run = [(c, a) for (c, a) in self.get_checks() if c.fixable]
        nissues = 0
        nfixed = 0
        for check, arg in checks_to_run:
            print(blue("[" + check.name() + "] "), end="", flush=True)
            problems = self.run_check(check, start, args=(arg,))
            nissues += len(problems)
            if problems:
                print(green("fixing"))
                for problem in problems:
                    if problem.autofix:
                        if not dry_run:
                            run(problem.autofix)
                        nfixed += 1
            else:
                print(green("no issues"))

        if not dry_run:
            run(["git", "add"] + self.get_repository().staged_files)

        print()
        print("Ran", blue(plural(len(checks_to_run), "check")), end=". ")
        print("Detected", red(plural(nissues, "issue")), end=". ")
        if dry_run:
            print(f"Would have fixed", green(f"{nfixed} of them") + ".")
        else:
            print("Fixed", green(f"{nfixed} of them."))

    @staticmethod
    def pattern_from_ext(ext):
        """Returns a regular expression pattern that matches string ending in `ext`."""
        return r".+\." + re.escape(ext)

    def get_checks(self):
        repository = self.get_repository()
        checks_to_run = []
        for check in self.checks:
            if check.slow and not self.check_all:
                continue

            if isinstance(check, RepoCheck):
                checks_to_run.append((check, repository))
            else:
                for matching_file in pathfilter(repository.staged_files, check.pattern):
                    checks_to_run.append((check, matching_file))

        return checks_to_run

    def run_check(self, check, start, *, args):
        if self.verbose:
            print(f"Running {check.name()}")

        check_start = time.monotonic()
        r = check.check(*args)
        check_end = time.monotonic()

        if self.verbose:
            elapsed = check_end - check_start
            elapsed_since_start = check_end - start
            print(f"Finished in {elapsed:.2f}s. ", end="")
            print(f"{elapsed_since_start:.2f}s since start.")

        if r is None:
            problems = []
        elif isinstance(r, list):
            problems = r
        else:
            problems = [r]

        for problem in problems:
            problem.checkname = check.name()

        return problems

    def get_repository(self):
        if self._repository is not None:
            return self._repository

        cmd = ["git", "diff", "--name-only", "--cached"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE)
        # For file paths that contain non-ASCII bytes or a literal double quote
        # character, Git encloses the path in double quotes and backslash-escapes the
        # offending character(s), so that the output of git diff is always valid ASCII.
        # We call `_git_path_as_bytes` on each path to get the original file path.
        staged_files = result.stdout.decode("ascii").splitlines()
        # TODO(2020-04-04): Handle UnicodeDecodeError here or elsewhere.
        staged_files = [
            GitPath.from_string(p).decode(self.encoding) for p in staged_files
        ]

        cmd = ["git", "diff", "--name-only"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE)
        unstaged_files = result.stdout.decode("ascii").splitlines()
        # TODO(2020-04-04): Handle UnicodeDecodeError here or elsewhere.
        unstaged_files = [
            GitPath.from_string(p).decode(self.encoding) for p in unstaged_files
        ]
        self._repository = Repository(
            staged_files=staged_files, unstaged_files=unstaged_files
        )
        return self._repository


class BaseCheck:
    """The base class for pre-commit checks.

    Custom checks should inherit from either `FileCheck` or `RepoCheck`.
    """

    fixable = False

    def name(self):
        return self.__class__.__name__

    def help(self):
        return self.__doc__


class RepoCheck(BaseCheck):
    """A base class for pre-commit checks that run once per repo."""


class FileCheck(BaseCheck):
    """A base class for pre-commit checks that run once per file."""

    pattern = None


def pathfilter(paths, pattern):
    """Filters the list of paths using the pattern."""
    # TODO: Handle the case where `pattern` is a regex object.
    if pattern is None:
        return paths
    else:
        return [p for p in paths if re.match(pattern, p)]


def run(args, *, merge_output=True):
    # args = [a.as_shell_arg() if isinstance(a, GitPath) else a for a in args]
    stderr = subprocess.STDOUT if merge_output else subprocess.PIPE
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=stderr)


class GitPath(bytes):
    @classmethod
    def from_string(cls, path):
        """Converts a path string as Git displays it to the original bytes of the path.

        If the file path contains a non-ASCII character or a literal double quote, Git
        backslash-escapes the offending character and encloses the whole path in double
        quotes. This function reverses that transformation to get the original bytes.
        """
        if path.startswith('"') and path.endswith('"'):
            return cls(ast.literal_eval("b" + path))
        else:
            return cls(path.encode("ascii"))

    def as_string(self):
        """Converts the path to a string for display."""
        try:
            return self.decode("utf-8")
        except UnicodeDecodeError:
            return repr(self)[1:]

    def as_shell_arg(self):
        """Converts the path to a string suitable to be passed to a shell command."""
        return repr(self)[1:]


def print_problem(problem):
    builder = []
    # builder.append(red(f"[{problem.checkname}] "))
    if problem.path:
        builder.append(blue(problem.path))
        builder.append(": ")
    builder.append(problem.message)
    print("".join(builder))
    if problem.verbose_message:
        print()
        print(textwrap.indent(problem.verbose_message, "  "))
        print()


class Problem:
    def __init__(self, message, *, checkname=None, autofix=None, verbose_message=None):
        self.path = None
        self.checkname = checkname
        self.message = message
        self.autofix = autofix
        self.verbose_message = verbose_message


Repository = namedtuple("Repository", ["staged_files", "unstaged_files"])


_COLOR_RED = "91"
_COLOR_BLUE = "94"
_COLOR_GREEN = "92"
_COLOR_RESET = "0"
_NO_COLOR = False


def turn_on_colors():
    """Turns on colored output globally for the program."""
    global _NO_COLOR
    _NO_COLOR = False


def turn_off_colors():
    """Turns off colored output globally for the program."""
    global _NO_COLOR
    _NO_COLOR = True


def red(text):
    """Returns a string that will display as red using ANSI color codes."""
    return colored(text, _COLOR_RED)


def blue(text):
    """Returns a string that will display as blue using ANSI color codes."""
    return colored(text, _COLOR_BLUE)


def green(text):
    """Returns a string that will display as green using ANSI color codes."""
    return colored(text, _COLOR_GREEN)


def colored(text, color):
    return f"\033[{color}m{text}\033[{_COLOR_RESET}m" if not _NO_COLOR else text


def plural(n, word, suffix="s"):
    """Returns the numeral and the proper plural form of the word."""
    return f"{n} {word}" if n == 1 else f"{n} {word}{suffix}"


class UsageError(Exception):
    """Exception for incorrect usage of the precommit API."""
