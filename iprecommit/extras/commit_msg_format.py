import argparse
import sys
import textwrap
from pathlib import Path
from typing import Optional


def main(argv=None) -> None:
    argparser = argparse.ArgumentParser(
        description="Check the format of the commit message."
    )
    argparser.add_argument(
        "file", help="The file holding the contents of the commit message."
    )
    argparser.add_argument(
        "--max-first-line-length", type=int, help="Max length of first line of message"
    )
    argparser.add_argument(
        "--max-line-length",
        type=int,
        help="Max length of each line (can be overridden for first line by --max-first-line-length)",
    )
    argparser.add_argument(
        "--require-capitalized",
        action="store_true",
        help="Require the first line to begin with a capital letter.",
    )
    args = argparser.parse_args(argv)

    message = Path(args.file).read_text()
    passed = check(
        message,
        max_first_line_length=args.max_first_line_length,
        max_line_length=args.max_line_length,
        require_capitalized=args.require_capitalized,
    )
    if not passed:
        sys.exit(2)


def check(
    text: str,
    *,
    max_first_line_length: Optional[int],
    max_line_length: Optional[int],
    require_capitalized: bool,
) -> bool:
    if not text:
        print("commit message is empty")
        return False

    passed = True
    first_line, *lines = text.splitlines()

    if not first_line:
        print("first line should not be blank")
        passed = False

    if first_line and first_line[0].isspace():
        print("first line should not start with whitespace")
        passed = False

    if len(lines) > 0 and lines[0] != "":
        print("should be a blank line after first line")
        passed = False

    if max_first_line_length is None:
        max_first_line_length = max_line_length

    if max_first_line_length is not None:
        line_ok = check_line(1, first_line, max_first_line_length)
        if not line_ok:
            passed = False

    if max_line_length is not None:
        for lineno, line in enumerate(lines, start=2):
            line_ok = check_line(lineno, line, max_line_length)
            if not line_ok:
                passed = False

    if require_capitalized and (first_line and first_line[0].islower()):
        print("first line should be capitalized")
        passed = False

    return passed


def check_line(lineno: int, line: str, max_length: int) -> bool:
    if len(line) > max_length:
        trunc = textwrap.shorten(line, width=15, placeholder="...")
        print(f"line {lineno} too long: len={len(line)}, max={max_length}: {trunc}")
        return False
    else:
        return True
