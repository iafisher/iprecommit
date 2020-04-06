import ast
import re
import subprocess
import sys
import textwrap
import time
from collections import namedtuple


class Precommit:
    def __init__(self, *, output, check_all):
        self.encoding = "utf-8"
        self.output = output
        self.checks = []
        self.verbose = False
        self.check_all = False
        # Cached result of self.get_repository()
        self._repository = None

    @classmethod
    def from_args(cls, args):
        dry_run = args.flags.get("--dry-run", False)
        output = (
            VerboseOutput(dry_run=dry_run)
            if args.flags.get("--verbose")
            else NormalOutput(dry_run=dry_run)
        )
        check_all = args.flags.get("--all", False)
        return cls(output=output, check_all=check_all)

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
        self.output.start()
        checks_to_run = self.get_checks()
        problems = []
        for check, arg in checks_to_run:
            self.output.check_name(check)
            new_problems = self.run_check(check, args=(arg,))
            problems.extend(new_problems)
            if new_problems:
                for problem in new_problems:
                    self.output.problem(problem)
            else:
                self.output.no_problem()

        fixable_problems = [problem for problem in problems if problem.autofix]
        self.output.summary_for_check(len(fixable_problems), len(problems))
        if problems:
            sys.exit(1)

    def fix(self, *, dry_run=False):
        checks_to_run = [(c, a) for (c, a) in self.get_checks() if c.fixable]
        nissues = 0
        nfixed = 0
        for check, arg in checks_to_run:
            self.output.check_name(check)
            problems = self.run_check(check, args=(arg,))
            nissues += len(problems)
            if problems:
                self.output.fixing()
                for problem in problems:
                    if problem.autofix:
                        if not dry_run:
                            run(problem.autofix)
                        nfixed += 1
            else:
                self.output.no_problem()

        if not dry_run:
            run(["git", "add"] + self.get_repository().staged_files)

        self.output.summary_for_fix(len(checks_to_run), nissues, nfixed)

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

    def run_check(self, check, *, args):
        self.output.start_check(check)
        r = check.check(*args)
        self.output.end_check()

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


class Problem:
    def __init__(self, message, *, checkname=None, autofix=None, verbose_message=None):
        self.path = None
        self.checkname = checkname
        self.message = message
        self.autofix = autofix
        self.verbose_message = verbose_message


class NormalOutput:
    def __init__(self, *, dry_run=False):
        self.dry_run = dry_run

    def check_name(self, check):
        print(blue("[" + check.name() + "] "), end="", flush=True)

    def problem(self, problem):
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

    def no_problem(self):
        print("no issues")

    def summary_for_check(self, nfixable, ntotal):
        if ntotal > 0:
            print()
            print(f"{red(plural(ntotal, 'issue'))} found. ", end="")

            if nfixable > 0:
                if nfixable == ntotal:
                    n = green("all of them")
                else:
                    n = blue(f"{nfixable} of them")

                print(f"Fix {n} with '{blue('precommit fix')}'.", end="")

            print()
        else:
            print(f"{green('No issues')} detected.")

    def fixing(self):
        print(green("fixing"))

    def summary_for_fix(self, nchecks, nissues, nfixed):
        print()
        print("Ran", blue(plural(nchecks, "check")), end=". ")
        print("Detected", red(plural(nissues, "issue")), end=". ")
        if self.dry_run:
            print(f"Would have fixed", green(f"{nfixed} of them") + ".")
        else:
            print("Fixed", green(f"{nfixed} of them."))

    def start(self):
        pass

    def start_check(self, check):
        pass

    def end_check(self):
        pass


class VerboseOutput(NormalOutput):
    def start(self):
        self.start = time.monotonic()

    def start_check(self, check):
        print(f"Running {check.name()}")
        self.check_start = time.monotonic()

    def end_check(self):
        check_end = time.monotonic()
        elapsed = check_end - self.check_start
        elapsed_since_start = check_end - self.start
        print(f"Finished in {elapsed:.2f}s. ", end="")
        print(f"{elapsed_since_start:.2f}s since start.")


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
