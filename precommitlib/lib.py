import ast
import copy
import re
import subprocess
import sys
import textwrap
import time


class Precommit:
    def __init__(self, checks, *, console, fs, check_all, dry_run):
        """
        Parameters:
          checks: The list of checks to run.
          console: The interface to the console (for showing output).
          fs: The interface to the file system (for running commands).
          check_all: Whether to run all checks.
          dry_run: Whether to actually run fix commands or just pretend to.
        """
        self.console = console
        self.fs = fs
        self.checks = checks
        self.check_all = check_all
        self.dry_run = dry_run

    @classmethod
    def from_args(cls, checks, args):
        console_cls = VerboseConsole if args.flags["--verbose"] else Console
        console = console_cls.from_args(args)
        fs = Filesystem()
        return cls(
            checks,
            console=console,
            fs=fs,
            check_all=args.flags["--all"],
            dry_run=args.flags["--dry-run"],
        )

    def check(self):
        """Find problems and print a message for each."""
        self.console.start()
        repository = self.get_repository()
        checks_to_run = self.get_checks(repository)
        for check, arg in checks_to_run:
            problems = self.execute_check(check, arg)
            self.console.post_check_for_check_subcommand(problems)
        self.console.summary_for_check()

    def fix(self):
        """Find problems and fix the ones that can be fixed automatically."""
        self.console.start()
        repository = self.get_repository()
        checks_to_run = [(c, a) for (c, a) in self.get_checks(repository) if c.fixable]
        for check, arg in checks_to_run:
            problems = self.execute_check(check, arg)
            self.console.post_check_for_fix_subcommand(problems)
            if not self.dry_run:
                for problem in problems:
                    if problem.autofix:
                        self.fs.run(problem.autofix)

        if not self.dry_run:
            self.fs.run(["git", "add"] + repository.staged)

        self.console.summary_for_fix()

    def get_checks(self, repository):
        checks_to_run = []
        for check in self.checks:
            if check.slow and not self.check_all:
                continue

            filtered = pathfilter(repository.staged, check.pattern, check.exclude)
            if filtered:
                if isinstance(check, RepoCheck):
                    repository = copy.copy(repository)
                    repository.filtered = filtered
                    checks_to_run.append((check, repository))
                else:
                    checks_to_run.append((check, filtered))

        return checks_to_run

    def execute_check(self, check, arg):
        self.console.pre_check(check)
        problems = check.check_wrapper(arg)
        self.console.post_check()

        for problem in problems:
            problem.checkname = check.name()

        return problems

    def get_repository(self):
        staged = self.fs.get_staged_files()
        staged_deleted = self.fs.get_staged_for_deletion_files()
        unstaged = self.fs.get_unstaged_files()
        return Repository(
            staged=staged, staged_deleted=staged_deleted, unstaged=unstaged
        )


class Checklist:
    def __init__(self):
        self.checks = []

    def check(self, check, *, pattern=None, exclude=None, slow=False, fatal=False):
        """Registers the pre-commit check.

        Args:
          check: The check object itself.
          pattern: A regular expression pattern, as a string. If not None, then the
            check will only run on file paths which match this pattern.
          exclude: A regular expression pattern as a string. If not None, then the check
            will not run on file paths which match the pattern.
          slow: Whether the check is expected to be slow or not. If True, then the check
            will not be invoked unless the precommit command is invoked with the --all
            flag. By default, the pre-commit hook that is installed in git uses the
            --all flag.
          fatal: Whether a check failure should immediately end the pre-commit check.
        """
        if not isinstance(check, (FileCheck, RepoCheck)):
            raise UsageError("check must be a subclass of FileCheck or RepoCheck")

        check.slow = slow
        check.fatal = fatal
        if pattern is not None:
            check.pattern = pattern
        if exclude is not None:
            check.exclude = exclude

        self.checks.append(check)


def pattern_from_ext(ext):
    """Returns a regular expression pattern that matches string ending in `ext`."""
    return r"^.+\." + re.escape(ext) + "$"


class BaseCheck:
    """The base class for pre-commit checks.

    Custom checks should inherit from either `FileCheck` or `RepoCheck`.
    """

    fixable = False
    pattern = None
    exclude = None

    def check_wrapper(self, *args, **kwargs):
        raise NotImplementedError

    def name(self):
        return self.__class__.__name__

    def help(self):
        return self.__doc__

    @staticmethod
    def _normalize_result(r):
        if isinstance(r, Problem):
            return [r]
        elif r is None:
            return []
        else:
            return r


class RepoCheck(BaseCheck):
    """A base class for pre-commit checks that run once per repo."""

    def check_wrapper(self, repository):
        return self._normalize_result(self.check(repository))


class FileCheck(BaseCheck):
    """A base class for pre-commit checks that run once per file."""

    def check_wrapper(self, filtered):
        problems = []
        for path in filtered:
            results = self._normalize_result(self.check(path))
            for result in results:
                result.path = path
                problems.append(result)
        return problems


def pathfilter(paths, pattern, exclude):
    if pattern:
        regex = re.compile(pattern)
        filtered = [p for p in paths if regex.match(p)]
    else:
        filtered = paths

    if exclude:
        regex = re.compile(exclude)
        filtered = [p for p in filtered if not regex.match(p)]

    return filtered


def run(args, *, merge_output=True):
    stderr = subprocess.STDOUT if merge_output else subprocess.PIPE
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=stderr)


def decode_git_path(path):
    """Converts a path string as Git displays it to a UTF-8 encoded string.

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
    def __init__(self, message, *, checkname=None, autofix=None, verbose_message=None):
        self.path = None
        self.checkname = checkname
        self.message = message
        self.autofix = autofix
        self.verbose_message = verbose_message


class Filesystem:
    def stage_files(self, files):
        self.run(["git", "add"] + files)

    def get_staged_files(self):
        return self._read_files_from_git(["--cached", "--diff-filter=d"])

    def get_staged_for_deletion_files(self):
        return self._read_files_from_git(["--cached", "--diff-filter=D"])

    def get_unstaged_files(self):
        return self._read_files_from_git([])

    def run(self, cmd):
        return run(cmd)

    def _read_files_from_git(self, args):
        result = self.run(["git", "diff", "--name-only"] + args)
        return [decode_git_path(p) for p in result.stdout.decode("ascii").splitlines()]


class Console:
    def __init__(self, *, dry_run=False):
        self.dry_run = dry_run
        self.nchecks = 0
        self.problems = []
        self.printed_anything_yet = False

    @classmethod
    def from_args(cls, args):
        return cls(dry_run=args.flags["--dry-run"])

    def start(self):
        pass

    def pre_check(self, check):
        self.nchecks += 1
        self._print(blue("[" + check.name() + "] "), end="", flush=True)

    def post_check(self):
        pass

    def post_check_for_check_subcommand(self, problems):
        self.problems.extend(problems)
        if problems:
            for i, problem in enumerate(problems):
                self._problem(problem, with_checkname=bool(i > 0))
        else:
            self._print(green("passed!"))

    def post_check_for_fix_subcommand(self, problems):
        self.problems.extend(problems)
        if problems:
            self._print(green("fixing"))
        else:
            self._print(green("passed!"))

    def summary_for_check(self):
        fixable = sum(1 for p in self.problems if p.autofix)
        total = len(self.problems)
        if self.printed_anything_yet:
            self._print()
        self._print("Ran", blue(plural(self.nchecks, "check")), end=". ")
        if total > 0:
            self._print(f"Detected {red(plural(total, 'issue'))}", end=". ")

            if fixable > 0:
                if fixable == total:
                    n = green("all of them")
                else:
                    n = blue(f"{fixable} of them")

                self._print(f"Fix {n} with '{blue('precommit fix')}'.", end="")

            self._print()
            sys.exit(1)
        else:
            self._print(f"{green('No issues')} detected.")

    def summary_for_fix(self):
        fixable = sum(1 for p in self.problems if p.autofix)
        total = len(self.problems)
        if self.printed_anything_yet:
            self._print()
        self._print("Ran", blue(plural(self.nchecks, "fixable check")), end=". ")
        self._print("Detected", red(plural(total, "issue")), end=". ")
        if self.dry_run:
            self._print(f"Would have fixed", green(f"{fixable} of them") + ".")
        else:
            self._print("Fixed", green(f"{fixable} of them."))

    def _print(self, *args, **kwargs):
        self.printed_anything_yet = True
        print(*args, **kwargs)

    def _problem(self, problem, *, with_checkname=False):
        builder = []
        if with_checkname:
            builder.append(blue(f"[{problem.checkname}] "))
        builder.append(red("error"))
        builder.append(": ")
        if problem.path:
            builder.append(problem.path)
            builder.append(": ")
        builder.append(problem.message)
        self._print("".join(builder))
        if problem.verbose_message:
            self._print()
            self._print(textwrap.indent(problem.verbose_message, "  "))
            self._print()


class VerboseConsole(Console):
    def start(self):
        self.start = time.monotonic()

    def pre_check(self, check):
        self._print(f"Running {check.name()}")
        self.check_start = time.monotonic()
        super().pre_check(check)

    def post_check(self):
        self.check_end = time.monotonic()

    def post_check_for_check_subcommand(self, *args, **kwargs):
        super().post_check_for_check_subcommand(*args, **kwargs)
        elapsed = self.check_end - self.check_start
        elapsed_since_start = self.check_end - self.start
        self._print(f"Finished in {elapsed:.2f}s. ", end="")
        self._print(f"{elapsed_since_start:.2f}s since start.")

    def post_check_for_fix_subcommand(self, *args, **kwargs):
        super().post_check_for_check_subcommand(*args, **kwargs)
        elapsed = self.check_end - self.check_start
        elapsed_since_start = self.check_end - self.start
        self._print(f"Finished in {elapsed:.2f}s. ", end="")
        self._print(f"{elapsed_since_start:.2f}s since start.")


class Repository:
    def __init__(self, staged, staged_deleted, unstaged):
        self.staged = staged
        self.staged_deleted = staged_deleted
        self.unstaged = unstaged


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
