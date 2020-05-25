import ast
import fnmatch
import subprocess
import sys
import textwrap
import time

from . import utils


class Precommit:
    def __init__(self, checks, *, console, fs, check_all, dry_run, verbose):
        """
        Parameters:
          checks: The list of checks to run.
          console: The interface to the console (for showing output).
          fs: The interface to the file system (for running commands).
          check_all: Whether to run all checks.
          dry_run: Whether to actually run fix commands or just pretend to.
        """
        self._console = console
        self._fs = fs
        # Calling it `self._checks` instead of `self.checks` avoids giving a confusing
        # error message for the common typo of `precommit.checks(...)` instead of
        # `precommit.check(...)`.
        self._checks = checks
        self.check_all = check_all
        self.dry_run = dry_run
        self.verbose = verbose

        self.num_of_checks = 0
        self.num_of_problems = 0
        self.num_of_fixable_problems = 0

    @classmethod
    def from_args(cls, checks, args):
        console = Console()
        fs = Filesystem.from_args(console, args)
        return cls(
            checks,
            console=console,
            fs=fs,
            check_all=args.flags["--all"],
            dry_run=args.flags["--dry-run"],
            verbose=args.flags["--verbose"],
        )

    def check(self):
        """Find problems and print a message for each."""
        if not self._checks:
            self._console.print("No checks were registered.")
            return

        self.start = time.monotonic()
        repository = self.get_repository()
        if not (repository.staged or repository.staged_deleted):
            self._console.print("No files are staged.")
            return

        for check in self._checks:
            if not self.should_run(check):
                if self.verbose:
                    self.print_check_header_and_status(check, "skipped")
                continue

            if not check.filter(repository.staged):
                if self.verbose:
                    self.print_check_header_and_status(check, "skipped")
                continue

            self.pre_check(check)
            problem = check.check(self._fs, repository)
            status = utils.red("failed!") if problem else utils.green("passed!")
            self.post_check(check, status, problem)

        self.print_summary_for_check()
        return self.num_of_problems > 0

    def fix(self):
        """Find problems and fix the ones that can be fixed automatically."""
        if not self._checks:
            self._console.print("No checks were registered.")
            return

        self.start = time.monotonic()
        repository = self.get_repository()
        if not (repository.staged or repository.staged_deleted):
            self._console.print("No files are staged.")
            return

        for check in self._checks:
            if not check.is_fixable():
                continue

            if not self.should_run(check):
                if self.verbose:
                    self.print_check_header_and_status(check, "skipped")
                continue

            if not check.filter(repository.staged):
                if self.verbose:
                    self.print_check_header_and_status(check, "skipped")
                continue

            self.pre_check(check)
            problem = check.check(self._fs, repository)

            if not self.dry_run:
                if problem and problem.autofix:
                    self._fs.run(problem.autofix)

            status = utils.green("fixed!") if problem else utils.green("passed!")
            self.post_check(check, status, problem)

        if not self.dry_run:
            self._fs.run(["git", "add"] + repository.staged)

        self.print_summary_for_fix()

    def print_summary_for_check(self):
        self._console.print()
        self._console.print(
            "Ran", utils.blue(utils.plural(self.num_of_checks, "check")), end=". "
        )
        if self.num_of_problems > 0:
            self._console.print(
                f"Detected {utils.red(utils.plural(self.num_of_problems, 'issue'))}",
                end=". ",
            )

            if self.num_of_fixable_problems > 0:
                if self.num_of_fixable_problems == self.num_of_problems:
                    n = utils.green("all of them")
                else:
                    n = utils.blue(f"{self.num_of_fixable_problems} of them")

                self._console.print(
                    f"Fix {n} with '{utils.blue('precommit fix')}'.", end=""
                )

            self._console.print()
        else:
            self._console.print(f"{utils.green('No issues')} detected.")

    def print_summary_for_fix(self):
        self._console.print()
        self._console.print(
            "Ran",
            utils.blue(utils.plural(self.num_of_checks, "fixable check")),
            end=". ",
        )
        self._console.print(
            "Detected", utils.red(utils.plural(self.num_of_problems, "issue")), end=". "
        )
        if self.dry_run:
            self._console.print(
                f"Would have fixed",
                utils.green(f"{self.num_of_fixable_problems} of them") + ".",
            )
        else:
            self._console.print(
                "Fixed " + utils.green(f"{self.num_of_fixable_problems} of them") + "."
            )

    def pre_check(self, check):
        if self.verbose:
            self._console.print(f"Running {check.get_name()}")
            self.check_start = time.monotonic()

        self.num_of_checks += 1
        self.print_check_header(check)

    def post_check(self, check, status, problem):
        if problem is not None:
            self.num_of_problems += 1
            if check.is_fixable():
                self.num_of_fixable_problems += 1

        self.print_check_status(status)

        if self.verbose:
            self.check_end = time.monotonic()
            elapsed = self.check_end - self.check_start
            elapsed_since_start = self.check_end - self.start
            self._console.print(f"Finished in {elapsed:.2f}s. ", end="")
            self._console.print(f"{elapsed_since_start:.2f}s since start.")

        self._console.print()

    def print_check_header_and_status(self, check, status):
        self.print_check_header(check)
        self.print_check_status(status)
        self._console.print()

    def print_check_header(self, check):
        self._console.print(utils.blue("o--[ " + check.get_name() + " ]"))

    def print_check_status(self, status):
        self._console.print(utils.blue("o--[ ") + status + utils.blue(" ]"))

    def should_run(self, check):
        return not check.slow or self.check_all

    def get_repository(self):
        staged = self._fs.get_staged_files()
        staged_deleted = self._fs.get_staged_for_deletion_files()
        unstaged = self._fs.get_unstaged_files()
        return Repository(
            staged=staged, staged_deleted=staged_deleted, unstaged=unstaged
        )


class Checklist:
    def __init__(self):
        self._checks = []

    def check(self, check):
        """Registers the pre-commit check."""
        if not isinstance(check, BaseCheck):
            raise UsageError("check must be a subclass of BaseCheck")

        self._checks.append(check)


class BaseCheck:
    def __init__(self, slow=False, include=None, exclude=None):
        if isinstance(include, str):
            raise UsageError("include should be a list of strings")

        if isinstance(exclude, str):
            raise UsageError("exclude should be a list of strings")

        self.slow = slow
        self.include = include if include is not None else []
        self.exclude = exclude if exclude is not None else []

    def check(self, fs, repository):
        raise NotImplementedError

    def get_name(self):
        return self.__class__.__name__

    def is_fixable(self):
        return False

    def filter(self, paths):
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
        self._console = console
        self.verbose = verbose
        # This is a function because the test suite turns off colors after the program
        # starts, but if we assign `blue("|  ")` to a class attribute then it gets
        # colored before the colors are turned off.
        self.prefix = utils.blue("|  ")

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

    def print(self, msg):
        self._console.print(textwrap.indent(msg, self.prefix))

    def run(self, cmd, *, capture_output=True):
        if self.verbose:
            self._console.print("Running command: " + " ".join(cmd))

        if capture_output:
            return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        else:
            # Normally this isn't necessary, but sometimes when you pipe precommit
            # itself to another command or to a file (as the functional test does), then
            # it will print all the output of the command below before any of
            # precommit's output, for reasons that remain obscure to me.
            sys.stdout.flush()

            # Print the prefix before each line of the command's output by piping it to
            # sed.
            ps = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            subprocess.run(
                ["sed", "-e", "s/^/" + self.prefix + "/"],
                stdin=ps.stdout,
                stderr=subprocess.STDOUT,
            )
            return ps.wait()

    def _read_files_from_git(self, args):
        result = self.run(["git", "diff", "--name-only"] + args)
        return [decode_git_path(p) for p in result.stdout.decode("ascii").splitlines()]


class Console:
    def print(self, *args, **kwargs):
        print(*args, **kwargs)


class Repository:
    def __init__(self, staged, staged_deleted, unstaged):
        self.staged = staged
        self.staged_deleted = staged_deleted
        self.unstaged = unstaged


class UsageError(Exception):
    """Exception for incorrect usage of the precommit API."""
