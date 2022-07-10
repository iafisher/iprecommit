"""
Utility functions and constants for the precommit tool.
"""
import sys


# A global flag indicating whether --verbose was passed.
VERBOSE = False


def plural(n: int, word: str, suffix: str = "s") -> str:
    """Returns the numeral and the proper plural form of the word."""
    return f"{n} {word}" if n == 1 else f"{n} {word}{suffix}"


def error(message: str) -> None:
    """
    Prints an error message and exits the program.
    """
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


def turn_off_colors() -> None:
    """Turns off colored output globally for the program."""
    global _NO_COLOR
    _NO_COLOR = True


def red(text: str) -> str:
    """Returns a string that will display as red using ANSI color codes."""
    return _colored(text, _COLOR_RED)


def blue(text: str) -> str:
    """Returns a string that will display as blue using ANSI color codes."""
    return _colored(text, _COLOR_BLUE)


def green(text: str) -> str:
    """Returns a string that will display as green using ANSI color codes."""
    return _colored(text, _COLOR_GREEN)


def yellow(text: str) -> str:
    """Returns a string that will display as yellow using ANSI color codes."""
    return _colored(text, _COLOR_YELLOW)


def _colored(text: str, color: str) -> str:
    return f"\033[{color}m{text}\033[{_COLOR_RESET}m" if not _NO_COLOR else text


_COLOR_RED = "91"
_COLOR_BLUE = "94"
_COLOR_GREEN = "92"
_COLOR_YELLOW = "93"
_COLOR_RESET = "0"
_NO_COLOR = False
