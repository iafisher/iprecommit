import ast
import re
import subprocess
import textwrap
import time


class Precommit:
    def __init__(self, checks, *, output, fs, check_all, dry_run):
        """
        Parameters:
          checks: The list of checks to run.
          output: The interface to the console (for showing output).
          fs: The interface to the file system (for running commands).
          check_all: Whether to run all checks.
          dry_run: Whether to actually run fix commands or just pretend to.
        """
        self.output = output
        self.fs = fs
        self.checks = checks
        self.check_all = check_all
        self.dry_run = dry_run

    @classmethod
    def from_args(cls, checks, args):
        console = Console()
        output = Output.from_args(console, args)
        fs = Filesystem.from_args(console, args)
        return cls(
            checks,
            output=output,
            fs=fs,
            check_all=args.flags["--all"],
            dry_run=args.flags["--dry-run"],
        )

    def check(self):
        """Find problems and print a message for each."""
        if not self.checks:
            self.output.no_checks()
            return

        self.output.start()
        repository = self.get_repository()
        if not (repository.staged or repository.staged_deleted):
            self.output.no_files()
            return

        found_problems = False
        for check in self.checks:
            if not self.should_run(check):
                continue

            problem = self.execute_check("check", check, repository)
            if problem is not None:
                found_problems = True

        self.output.summary("check")
        return found_problems

    def fix(self):
        """Find problems and fix the ones that can be fixed automatically."""
        if not self.checks:
            self.output.no_checks()
            return

        self.output.start()
        repository = self.get_repository()
        if not (repository.staged or repository.staged_deleted):
            self.output.no_files()
            return

        for check in self.checks:
            if not self.should_run(check) or not check.is_fixable():
                continue

            problem = self.execute_check("fix", check, repository)
            if not self.dry_run:
                if problem and problem.autofix:
                    self.fs.run(problem.autofix)

        if not self.dry_run:
            self.fs.run(["git", "add"] + repository.staged)

        self.output.summary("fix")

    def execute_check(self, subcommand, check, repository):
        if not check.filter(repository.staged):
            return None

        self.output.pre_check(subcommand, check)
        problem = check.check(self.fs, repository)
        self.output.post_check(subcommand, check, problem)
        return problem

    def should_run(self, check):
        return not check.slow or self.check_all

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

    def check(self, check):
        """Registers the pre-commit check."""
        if not isinstance(check, BaseCheck):
            raise UsageError("check must be a subclass of BaseCheck")

        self.checks.append(check)


class BaseCheck:
    def __init__(self, slow=False, pattern=None, exclude=None):
        self.slow = slow
        self.pattern = pattern
        self.exclude = exclude

    def check(self, repository):
        raise NotImplementedError

    def get_name(self):
        return self.__class__.__name__

    def is_fixable(self):
        return False

    def filter(self, paths):
        if self.pattern:
            regex = re.compile(self.pattern)
            filtered = [p for p in paths if regex.match(p)]
        else:
            filtered = paths

        if self.exclude:
            regex = re.compile(self.exclude)
            filtered = [p for p in filtered if not regex.match(p)]

        return filtered


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
    def __init__(self, autofix=None, message=None):
        self.autofix = autofix
        self.message = message


class Filesystem:
    def __init__(self, console, *, verbose):
        self.console = console
        self.verbose = verbose

    @classmethod
    def from_args(cls, console, args):
        return cls(console, verbose=args.flags["--verbose"])

    def get_staged_files(self):
        return self._read_files_from_git(["--cached", "--diff-filter=d"])

    def get_staged_for_deletion_files(self):
        return self._read_files_from_git(["--cached", "--diff-filter=D"])

    def get_unstaged_files(self):
        return self._read_files_from_git([])

    def open(self, *args, **kwargs):
        return open(*args, **kwargs)

    def run(self, cmd):
        if self.verbose:
            print("Running command: " + " ".join(cmd))

        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def _read_files_from_git(self, args):
        result = self.run(["git", "diff", "--name-only"] + args)
        return [decode_git_path(p) for p in result.stdout.decode("ascii").splitlines()]


class Console:
    def print(self, *args, **kwargs):
        print(*args, **kwargs)


class Output:
    def __init__(self, console, *, dry_run, verbose):
        self.console = console
        self.dry_run = dry_run
        self.verbose = verbose
        self.nchecks = 0
        self.problems = []

    @classmethod
    def from_args(cls, console, args):
        return cls(
            console, dry_run=args.flags["--dry-run"], verbose=args.flags["--verbose"]
        )

    def start(self):
        self.start = time.monotonic()

    def no_checks(self):
        self._print("No checks were registered.")

    def no_files(self):
        self._print("No files are staged.")

    def pre_check(self, subcommand, check):
        if self.verbose:
            self._print(f"Running {check.get_name()}")
            self.check_start = time.monotonic()

        self.nchecks += 1
        self._print(blue("o--[ " + check.get_name() + " ]"))

    def post_check(self, subcommand, check, problem):
        if problem is not None:
            self.problems.append((check.get_name(), problem))

        if problem and problem.message:
            self._print(blue("|"))
            self._print(textwrap.indent(problem.message, blue("|  "), lambda _: True))
            self._print(blue("|"))

        self._print(blue("o--[ "), end="")
        if subcommand == "check":
            if problem:
                self._print(red("failed!"), end="")
            else:
                self._print(green("passed!"), end="")
        elif subcommand == "fix":
            if problem:
                self._print(green("fixed!"), end="")
            else:
                self._print(green("passed!"), end="")
        self._print(blue(" ]"))

        if self.verbose:
            self.check_end = time.monotonic()
            elapsed = self.check_end - self.check_start
            elapsed_since_start = self.check_end - self.start
            self._print(f"Finished in {elapsed:.2f}s. ", end="")
            self._print(f"{elapsed_since_start:.2f}s since start.")

        self._print()

    def summary(self, subcommand):
        self._print()
        if subcommand == "check":
            self._summary_for_check()
        elif subcommand == "fix":
            self._summary_for_fix()

    def _summary_for_check(self):
        fixable = sum(1 for _, p in self.problems if p.autofix)
        total = len(self.problems)
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
        else:
            self._print(f"{green('No issues')} detected.")

    def _summary_for_fix(self):
        fixable = sum(1 for _, p in self.problems if p.autofix)
        total = len(self.problems)
        self._print("Ran", blue(plural(self.nchecks, "fixable check")), end=". ")
        self._print("Detected", red(plural(total, "issue")), end=". ")
        if self.dry_run:
            self._print(f"Would have fixed", green(f"{fixable} of them") + ".")
        else:
            self._print("Fixed", green(f"{fixable} of them."))

    def _print(self, *args, **kwargs):
        self.console.print(*args, **kwargs)


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
