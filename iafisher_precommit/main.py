import os
import stat
import sys
from collections import namedtuple

from .lib import blue, run, turn_off_colors, turn_on_colors


def main():
    args = handle_args(sys.argv[1:])

    chdir_to_git_root()
    if args.subcommand == "init":
        main_init(args)
    elif args.subcommand == "fix":
        main_fix(args)
    elif args.subcommand == "list":
        main_list(args)
    elif args.subcommand == "help":
        main_help(args)
    else:
        main_check(args)


def main_init(args):
    # TODO: Check that precommit.py doesn't exist first to avoid overwriting it.
    with open("precommit.py", "w", encoding="utf-8") as f:
        f.write(PRECOMMIT)

    # TODO: Check that .git/hooks/pre-commit doesn't exist first.
    hookpath = os.path.join(".git", "hooks", "pre-commit")
    with open(hookpath, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\n\nprecommit\n")

    # Make the hook executable by everyone.
    st = os.stat(hookpath)
    os.chmod(hookpath, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main_fix(args):
    precommit = get_precommit(args)
    precommit.fix()


def main_list(args):
    precommit = get_precommit(args)

    for check in precommit.repo_checks + precommit.file_checks:
        print(blue("[" + check.name() + "] "), end="")
        doc = check.help() or "no description available"
        print(doc)


def main_help(args):
    print(HELP)


def main_check(args):
    precommit = get_precommit(args)
    precommit.check()


def chdir_to_git_root():
    gitroot = run(["git", "rev-parse", "--show-toplevel"])
    if gitroot.returncode != 0:
        error("must be in git repository.")
    os.chdir(gitroot.stdout.decode("ascii").strip())


SUBCOMMANDS = {"init", "fix", "list", "help"}
FLAGS = {"--color", "--no-color", "-h", "--help", "--verbose"}
UnprocessedArgs = namedtuple("UnprocessedArgs", ["positional", "flags"])
ProcessedArgs = namedtuple("ProcessedArgs", ["subcommand", "flags"])


def handle_args(args):
    # Check for the NO_COLOR environment variable because handling command-line
    # arguments so that it can be overridden by explicitly specifying --color.
    if "NO_COLOR" in os.environ:
        turn_off_colors()

    args = parse_args(args)
    errormsg = check_args(args)
    if errormsg:
        error(errormsg)

    if args.flags.get("--color"):
        turn_on_colors()
    elif args.flags.get("--no-color"):
        turn_off_colors()

    subcommand = args.positional[0] if args.positional else None
    if args.flags.get("-h") or args.flags.get("--help"):
        subcommand = "help"
    return ProcessedArgs(subcommand=subcommand, flags=args.flags)


def parse_args(args):
    positional = []
    flags = {}
    force_positional = False
    for arg in sys.argv[1:]:
        if arg == "--":
            force_positional = True
            continue
        elif not force_positional and arg.startswith("-"):
            flags[arg] = True
        else:
            positional.append(arg)

    return UnprocessedArgs(flags=flags, positional=positional)


def check_args(args):
    if len(args.positional) > 1:
        return "too many positional arguments"

    if args.positional and args.positional[0] not in SUBCOMMANDS:
        return f"unknown subcommand: {args.positional[0]}"

    if "--no-color" in args.flags and "--color" in args.flags:
        return "--color and --no-color are incompatible"

    for flag in args.flags:
        if flag not in FLAGS:
            return f"unknown flag: {flag}"

    return None


def get_precommit(args):
    sys.path.append(os.getcwd())
    try:
        from precommit import main
    except ImportError:
        message = (
            "could not find precommit.py with main function. "
            + "You can create one by running 'precommit init'."
        )
        error(message)
    else:
        precommit = main()
        precommit.set_args(args)
        return precommit


def error(message):
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


PRECOMMIT = """\
from iafisher_precommit import checks, Precommit


def main():
    precommit = Precommit()

    # Generic checks
    precommit.register(checks.NoStagedAndUnstagedChanges())
    precommit.register(checks.NoWhitespaceInFilePath())

    # Python checks
    precommit.register(checks.PythonFormat())
    precommit.register(checks.PythonStyle())

    return precommit
"""


HELP = """\
precommit: simple git pre-commit hook management.

Usage: precommit [flags] [subcommand]

Subcommands:
    If left blank, subcommand defaults to 'check'.

    check           Check for precommit failures.
    fix             Apply any available fixes for problems that 'check' finds.
    init            Initialize
    help            Display a help message and exit.

Flags:
    --color         Turn on colorized output, overriding any environment settings.
    --no-color      Turn off colorized output.
    --verbose       Emit verbose output.
    -h, --help      Display a help message and exit.

Written by Ian Fisher. http://github.com/iafisher/precommit
"""
