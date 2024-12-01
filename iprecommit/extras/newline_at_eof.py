import argparse
import sys

from . import pathhelper


def main(argv=None) -> None:
    argparser = argparse.ArgumentParser(
        description="Check that each file ends with a newline."
    )
    argparser.add_argument("paths", nargs="+")
    group = argparser.add_mutually_exclusive_group()
    group.add_argument(
        "--disallow-empty",
        action="store_false",
        default=True,
        dest="allow_empty",
        help="Fail the check if any files are empty (zero bytes).",
    )
    group.add_argument(
        "--fix", action="store_true", help="Add a newline at the end of files."
    )
    args = argparser.parse_args(argv)

    passed = True
    for text, path in pathhelper.iterate_over_paths(args.paths):
        if not text:
            if args.fix or args.allow_empty:
                print(f"skipping empty file: {path}", file=sys.stderr)
            else:
                print(path)
                passed = False
        elif not text.endswith("\n"):
            if args.fix:
                with open(path, "a") as f:
                    f.write("\n")
                print(f"fixed: {path}")
            else:
                print(path)
                passed = False

    if not passed:
        sys.exit(2)
