"""
The command-line interface to the precommit tool.

Most of the tool's implementation lives in lib.py, and the definitions of the pre-commit
checks live in checks.py.

Author:  Ian Fisher (iafisher@fastmail.com)
Version: May 2020
"""
import importlib.util
import os
import pkg_resources
import shutil
import stat
import subprocess
import sys
from collections import namedtuple

from . import utils
from .lib import Checklist, Precommit


def main() -> None:
    args = parse_args(sys.argv[1:])
    configure_globals(args)

    chdir_to_git_root()
    if args.subcommand == "help" or args.flags["--help"]:
        main_help(args)
    elif args.subcommand == "init":
        main_init(args)
    elif args.subcommand == "fix":
        main_fix(args)
    else:
        main_check(args)


def main_init(args):
    if not args.flags["--force"] and os.path.exists("precommit.py"):
        utils.error("precommit.py already exists. Re-run with --force to overwrite it.")

    hookpath = os.path.join(".git", "hooks", "pre-commit")
    if not args.flags["--force"] and os.path.exists(hookpath):
        utils.error(f"{hookpath} already exists. Re-run with --force to overwrite it.")

    # Courtesy of https://setuptools.readthedocs.io/en/latest/pkg_resources.html
    template_path = pkg_resources.resource_filename(__name__, "precommit.py.template")
    shutil.copyfile(template_path, "precommit.py")

    with open(hookpath, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\n\nprecommit --all\n")

    # Make the hook executable by everyone.
    st = os.stat(hookpath)
    os.chmod(hookpath, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main_fix(args):
    precommit = get_precommit(args)
    precommit.fix()


def main_help(args):
    print(HELP)


def main_check(args):
    precommit = get_precommit(args)
    found_problems = precommit.check()
    if found_problems:
        sys.exit(1)


def chdir_to_git_root():
    gitroot = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if gitroot.returncode != 0:
        utils.error("must be in git repository.")
    os.chdir(gitroot.stdout.decode("ascii").strip())


SUBCOMMANDS = {"init", "fix", "help", "check"}
SHORT_FLAGS = {"-f": "--force", "-h": "--help", "-w": "--working"}
FLAGS = {
    "--color": set(),
    "--no-color": set(),
    "--help": set(),
    "--verbose": {"fix", "check"},
    "--all": {"fix", "check"},
    "--force": {"init"},
    "--working": {"fix", "check"},
}
Args = namedtuple("Args", ["subcommand", "positional", "flags"])


def parse_args(args):
    """
    Parses the argument list into an `Args` object.

    Exits the program with an error message if the arguments are invalid.
    """
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

    args = Args(subcommand=subcommand, flags=flags, positional=positional)

    errormsg = check_args(args)
    if errormsg:
        utils.error(errormsg)

    for flag in FLAGS:
        if flag not in args.flags:
            args.flags[flag] = False

    return args


def check_args(args):
    """
    Checks that the command-line arguments are valid.
    """
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


def configure_globals(args):
    """
    Configure global settings based on the command-line arguments.
    """
    # Check for the NO_COLOR environment variable and for a non-terminal standard output
    # before handling command-line arguments so that it can be overridden by explicitly
    # specifying --color.
    no_color = "NO_COLOR" in os.environ or not sys.stdout.isatty()

    if args.flags["--color"]:
        no_color = False
    elif args.flags["--no-color"]:
        no_color = True

    if no_color:
        utils.turn_off_colors()

    utils.VERBOSE = args.flags["--verbose"]


def get_precommit(args):
    path = os.path.join(os.getcwd(), "precommit.py")
    try:
        # Courtesy of https://stackoverflow.com/questions/67631/
        # We could add the current directory to `sys.path` and use a regular import
        # statement, but then if there's no `precommit.py` file in the right place, but
        # there is one somewhere else on `sys.path`, Python will import that module
        # instead and the user will be very confused (#28). The technique below
        # guarantees that an exception will be raised if there is no `precommit.py` in
        # the expected place.
        spec = importlib.util.spec_from_file_location("precommit", path)
        precommit_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(precommit_module)
    except (FileNotFoundError, ImportError):
        utils.error(
            "could not find precommit.py. You can create it with 'precommit init'."
        )
    else:
        # Call the user's code to initialize the checklist.
        checklist = Checklist()
        precommit_module.init(checklist)

        precommit = Precommit(
            checklist._checks,
            check_all=args.flags["--all"],
            working=args.flags["--working"],
        )
        return precommit


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
    -w, --working   Run on unstaged as well as staged changes.
    -h, --help      Display a help message and exit.

Written by Ian Fisher. http://github.com/iafisher/precommit"""
