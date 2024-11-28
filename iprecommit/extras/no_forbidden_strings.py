import argparse
import re
import sys
from pathlib import Path

from . import githelper

# written like this so this file doesn't trigger the check itself
DEFAULT_FORBIDDEN = ["DO NOT " + "COMMIT", "DO NOT " + "SUBMIT"]


def main(argv=None) -> None:
    forbidden_set = ", ".join(map(repr, DEFAULT_FORBIDDEN))
    argparser = argparse.ArgumentParser(
        description="Check that no file (or commit) contains any of the given forbidden strings (case-insensitive). "
        + f"By default, [{forbidden_set}] are forbidden."
    )
    argparser.add_argument("--paths", nargs="*", default=[])
    argparser.add_argument(
        "--commits",
        nargs="*",
        default=[],
        help="Check the commit messages of these Git revisions.",
    )
    argparser.add_argument(
        "--strings",
        nargs="*",
        default=DEFAULT_FORBIDDEN,
        help="Strings to forbid (overrides default).",
    )
    argparser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Make the matching case-sensitive.",
    )
    args = argparser.parse_args(argv)
    paths_and_commits = len(args.paths) > 0 and len(args.commits) > 0

    if args.case_sensitive:
        flags = 0
    else:
        flags = re.IGNORECASE

    pattern = re.compile("|".join(re.escape(s) for s in args.strings), flags=flags)

    passed = True
    for pathstr in args.paths:
        try:
            text = Path(pathstr).read_text()
        except IsADirectoryError:
            print(f"skipping directory: {pathstr}", file=sys.stderr)
            continue
        except UnicodeDecodeError:
            print(f"skipping non-UTF-8 file: {pathstr}", file=sys.stderr)

        if pattern.search(text) is not None:
            passed = False
            if paths_and_commits:
                print(f"path: {pathstr}")
            else:
                print(pathstr)

    for commit in args.commits:
        message = githelper.get_commit_message(commit)
        if pattern.search(message) is not None:
            passed = False
            if paths_and_commits:
                print(f"commit: {commit}")
            else:
                print(commit)

    if not passed:
        sys.exit(2)
