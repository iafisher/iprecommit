import os
import stat
import sys
from collections import namedtuple

from .lib import (
    Precommit,
    Output,
    VerboseOutput,
    blue,
    run,
    turn_off_colors,
    turn_on_colors,
)


def main():
    args = handle_args(sys.argv[1:])

    chdir_to_git_root()
    if args.subcommand == "help" or args.flags["--help"]:
        main_help(args)
    elif args.subcommand == "init":
        main_init(args)
    elif args.subcommand == "fix":
        main_fix(args)
    elif args.subcommand == "list":
        main_list(args)
    else:
        main_check(args)


def main_init(args):
    if not args.flags["--force"] and os.path.exists("precommit.py"):
        error("precommit.py already exists. Re-run with --force to overwrite it.")

    hookpath = os.path.join(".git", "hooks", "pre-commit")
    if not args.flags["--force"] and os.path.exists(hookpath):
        error(f"{hookpath} already exists. Re-run with --force to overwrite it.")

    with open("precommit.py", "w", encoding="utf-8") as f:
        f.write(PRECOMMIT)

    with open(hookpath, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\n\nprecommit --all\n")

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


SUBCOMMANDS = {"init", "fix", "list", "help", "check"}
SHORT_FLAGS = {"-f": "--force", "-h": "--help"}
FLAGS = {
    "--color": set(),
    "--no-color": set(),
    "--help": set(),
    "--verbose": {"fix", "check"},
    "--all": {"fix", "check"},
    "--force": {"init"},
    "--dry-run": {"fix"},
}
Args = namedtuple("Args", ["subcommand", "positional", "flags"])


def handle_args(args):
    # Check for the NO_COLOR environment variable and for a non-terminal standard output
    # before handling command-line arguments so that it can be overridden by explicitly
    # specifying --color.
    if "NO_COLOR" in os.environ and not sys.stdout.isatty():
        turn_off_colors()

    args = parse_args(args)
    errormsg = check_args(args)
    if errormsg:
        error(errormsg)

    for flag in FLAGS:
        if flag not in args.flags:
            args.flags[flag] = False

    if args.flags["--color"]:
        turn_on_colors()
    elif args.flags["--no-color"]:
        turn_off_colors()

    return args


def parse_args(args):
    positional = []
    flags = {}
    force_positional = False
    for arg in sys.argv[1:]:
        if arg == "--":
            force_positional = True
            continue
        elif not force_positional and arg.startswith("-"):
            if arg in SHORT_FLAGS:
                flags[SHORT_FLAGS[arg]] = True
            else:
                flags[arg] = True
        else:
            positional.append(arg)

    if positional:
        subcommand = positional[0]
        positional = positional[1:]
    else:
        subcommand = "check"

    return Args(subcommand=subcommand, flags=flags, positional=positional)


def check_args(args):
    if len(args.positional) > 0:
        return "precommit does not take positional arguments"

    if args.subcommand not in SUBCOMMANDS:
        return f"unknown subcommand: {args.subcommand}"

    if "--no-color" in args.flags and "--color" in args.flags:
        return "--color and --no-color are incompatible"

    for flag in args.flags:
        try:
            valid_subcommands = FLAGS[flag]
        except KeyError:
            return f"unknown flag: {flag}"
        else:
            # If `FLAGS[flag]` is the empty set, then it means the flag is valid for
            # any subcommand.
            if valid_subcommands and args.subcommand not in valid_subcommands:
                return f"flag {flag} not valid for {args.subcommand} subcommand"

    return None


def get_precommit(args):
    sys.path.append(os.getcwd())
    try:
        from precommit import init
    except ImportError:
        message = (
            "could not find precommit.py with init function. "
            + "You can create one by running 'precommit init'."
        )
        error(message)
    else:
        output = (VerboseOutput if args.flags["--verbose"] else Output).from_args(args)
        precommit = Precommit.from_args(output, args)
        init(precommit)
        return precommit


def error(message):
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


PRECOMMIT = """\
""\"Pre-commit configuration for git.

This file was created by precommit (https://github.com/iafisher/precommit).
You are welcome to edit it yourself to customize your pre-commit hook.
""\"
from precommitlib import checks


def init(precommit):
    # Generic checks
    precommit.register(checks.NoStagedAndUnstagedChanges())
    precommit.register(checks.NoWhitespaceInFilePath())
    precommit.register(checks.DoNotSubmit())

    # Python checks
    precommit.register(checks.PythonFormat())
    precommit.register(checks.PythonStyle())
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
    --all           Run all pre-commit checks, including slow ones.
    --color         Turn on colorized output, overriding any environment settings.
    --no-color      Turn off colorized output.
    --verbose       Emit verbose output.
    -h, --help      Display a help message and exit.

Written by Ian Fisher. http://github.com/iafisher/precommit"""
