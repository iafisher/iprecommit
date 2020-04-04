import argparse
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

    def set_args(self, args):
        self.verbose = args.flags.get("--verbose", False)

    def register(self, check, *, pattern=None):
        """Registers the check to run on files that match the regex `pattern`.

        `pattern` may be a string or a compiled regular expression object. If it is
        None, then the check will run on all files.
        """
        self.checks.append((check, pattern))
        if self.verbose:
            print(f"Registered check: {check.__class__.__name__}")

    def run(self):
        problems = self._find_problems()
        if problems:
            for problem in problems:
                _print_problem(problem)

            fixable_problems = [problem for problem in problems if problem.autofix]
            print(f"{_plural(len(problems), 'issue')} found. ", end="", file=sys.stderr)
            if fixable_problems:
                if len(fixable_problems) == len(problems):
                    n = _green("all of them")
                else:
                    n = _blue(f"{len(fixable_problems)} of them")

                print(f"Fix {n} with '{_blue('precommit fix')}'.", end="", file=sys.stderr)
            print(file=sys.stderr)
            sys.exit(1)
        else:
            print(f"{_green('No issues')} detected.", file=sys.stderr)

    @staticmethod
    def pattern_from_file_ext(ext):
        return r".+\." + re.escape(ext)

    def run_fix(self):
        raise NotImplementedError

    def _find_problems(self):
        start = time.monotonic()

        repo_info = self._get_repo_info()

        problems = []
        encoded_staged_files = []
        for path in repo_info.staged_files:
            try:
                encoded_staged_files.append(path.decode(self.encoding))
            except UnicodeDecodeError:
                problems.append(
                    Problem(
                        path=path,
                        message=f"file path is not valid for encoding {encoding!r}",
                    )
                )

        # TODO(2020-04-03): Shouldn't be checking unstaged files, although changing this
        # will make implementing checks that use unstaged_files harder because they
        # can't directly compare the path (string) to an unstaged file (bytes).
        encoded_unstaged_files = []
        for path in repo_info.unstaged_files:
            try:
                encoded_unstaged_files.append(path.decode(self.encoding))
            except UnicodeDecodeError:
                problems.append(
                    Problem(
                        path=path,
                        message=f"file path is not valid for encoding {encoding!r}",
                    )
                )

        if problems:
            return problems

        repo_info = repo_info._replace(
            staged_files=encoded_staged_files, unstaged_files=encoded_unstaged_files
        )
        for check, pattern in self.checks:
            if pattern is None and hasattr(check, "pattern"):
                pattern = check.pattern

            for matching_file in self._filter(repo_info.staged_files, pattern):
                if self.verbose:
                    print(f"Running {check.__class__.__name__} on {matching_file}")

                check_start = time.monotonic()
                r = check.check(repo_info, matching_file)
                check_end = time.monotonic()

                if self.verbose:
                    elapsed = check_end - check_start
                    elapsed_since_start = check_end - start
                    print(f"Finished in {elapsed:.2f}s. ", end="")
                    print(f"{elapsed_since_start:.2f}s since start.")

                if r is None:
                    continue
                elif isinstance(r, list):
                    for problem in r:
                        problem.path = matching_file
                    problems.extend(r)
                else:
                    r.path = matching_file
                    problems.append(r)

        return problems

    def _get_repo_info(self):
        cmd = ["git", "diff", "--name-only", "--cached"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE)
        # For file paths that contain non-ASCII bytes or a literal double quote
        # character, Git encloses the path in double quotes and backslash-escapes the
        # offending character(s), so that the output of git diff is always valid ASCII.
        # We call `_git_path_as_bytes` on each path to get the original file path.
        staged_files = result.stdout.decode("ascii").splitlines()
        staged_files = [GitPath.from_string(p) for p in staged_files]

        cmd = ["git", "diff", "--name-only"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE)
        unstaged_files = result.stdout.decode("ascii").splitlines()
        unstaged_files = [GitPath.from_string(p) for p in unstaged_files]
        return RepoInfo(
            encoding=self.encoding,
            staged_files=staged_files,
            unstaged_files=unstaged_files,
        )

    def _filter(self, files, pattern):
        # TODO: Handle the case where `pattern` is a regex object.
        if pattern is None:
            return files
        else:
            return [f for f in files if re.match(pattern, f)]


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


def _print_problem(problem):
    prefix = f"{_red('ERROR')} for {_blue(problem.path)}"
    print(f"{prefix}: {problem.message}", file=sys.stderr)
    if problem.verbose_message:
        print(file=sys.stderr)
        print(textwrap.indent(problem.verbose_message, "  "), file=sys.stderr)
        print(file=sys.stderr)


class Problem:
    def __init__(self, message, *, autofix=None, verbose_message=None):
        self.path = None
        self.message = message
        self.autofix = autofix
        self.verbose_message = verbose_message


RepoInfo = namedtuple("RepoInfo", ["encoding", "staged_files", "unstaged_files"])


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


def _red(text):
    """Returns a string that will display as red using ANSI color codes."""
    return _colored(text, _COLOR_RED)


def _blue(text):
    """Returns a string that will display as blue using ANSI color codes."""
    return _colored(text, _COLOR_BLUE)


def _green(text):
    """Returns a string that will display as green using ANSI color codes."""
    return _colored(text, _COLOR_GREEN)


def _colored(text, color):
    return f"\033[{color}m{text}\033[{_COLOR_RESET}m" if not _NO_COLOR else text


def _plural(n, word, suffix="s"):
    """Returns the numeral and the proper plural form of the word."""
    return f"{n} {word}" if n == 1 else f"{n} {word}{suffix}"
