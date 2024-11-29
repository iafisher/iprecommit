import argparse
import sys

from . import pathhelper


def main(argv=None) -> None:
    argparser = argparse.ArgumentParser(
        description="Check that each file ends with a newline."
    )
    argparser.add_argument("paths", nargs="+")
    argparser.add_argument(
        "--disallow-empty",
        action="store_false",
        default=True,
        dest="allow_empty",
        help="Fail the check if any files are empty (zero bytes).",
    )
    args = argparser.parse_args(argv)

    passed = True
    for text, display_title in pathhelper.iterate_over_paths_and_commits(
        args.paths, []
    ):
        if not text:
            if args.allow_empty:
                print(f"skipping empty file: {display_title}", file=sys.stderr)
            else:
                print(display_title)
                passed = False
        elif not text.endswith("\n"):
            print(display_title)
            passed = False

    if not passed:
        sys.exit(2)
