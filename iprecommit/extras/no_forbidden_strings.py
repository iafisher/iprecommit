import argparse
import re
import sys

from . import pathhelper

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

    if args.case_sensitive:
        flags = 0
    else:
        flags = re.IGNORECASE

    pattern = re.compile("|".join(re.escape(s) for s in args.strings), flags=flags)

    passed = True
    for text, display_title in pathhelper.iterate_over_paths_and_commits(
        args.paths, args.commits
    ):
        if pattern.search(text) is not None:
            passed = False
            print(display_title)

    if not passed:
        sys.exit(2)
