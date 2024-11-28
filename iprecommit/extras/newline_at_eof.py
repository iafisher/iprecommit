import argparse
import os
import sys


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
    for pathstr in args.paths:
        try:
            # TODO: only try text files and pass newline=None
            with open(pathstr, "rb") as f:
                try:
                    f.seek(-1, os.SEEK_END)
                except OSError:
                    if args.allow_empty:
                        print(f"skipping empty file: {pathstr}", file=sys.stderr)
                    else:
                        print(pathstr)
                        passed = False
                else:
                    b = f.read(1)

                    if b != b"\n":
                        print(pathstr)
                        passed = False
        except IsADirectoryError:
            print(f"skipping directory: {pathstr}", file=sys.stderr)

    if not passed:
        sys.exit(2)
