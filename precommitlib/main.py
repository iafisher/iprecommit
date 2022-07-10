"""
The command-line interface to the precommit tool.

Most of the tool's implementation lives in lib.py, and the definitions of the pre-commit
checks live in checks.py.
"""
import argparse
import importlib.util
import os
import pkg_resources
import shutil
import stat
import subprocess
import sys

from . import utils
from .lib import Checklist, Precommit


DESCRIPTION = """\
A simple tool to manage git pre-commit hooks.

Initialize the pre-commit checks (once per repo):

    precommit init

Run the pre-commit checks manually:

    precommit

Fix pre-commit violations:

    precommit fix

"""


def main() -> None:
    argparser = argparse.ArgumentParser(
        description=DESCRIPTION,
        # Prevent argparse from auto-formatting the description.
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    argparser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Emit verbose output.",
    )
    add_no_color_flag(argparser)

    subparsers = argparser.add_subparsers(metavar="subcmd")

    parser_check = subparsers.add_parser(
        "check", help="Check for pre-commit violations."
    )
    parser_check.add_argument(
        "--all",
        action="store_true",
        help="Run all pre-commit checks, including slow ones.",
    )
    parser_check.add_argument(
        "-w",
        "--working",
        action="store_true",
        help="Run on unstaged as well as staged changes.",
    )
    parser_check.set_defaults(func=main_check)
    add_no_color_flag(parser_check)

    parser_init = subparsers.add_parser(
        "init", help="Initialize the git pre-commit hook."
    )
    parser_init.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite an existing pre-commit hook.",
    )
    parser_init.set_defaults(func=main_init)

    parser_fix = subparsers.add_parser("fix", help="Fix pre-commit violations.")
    parser_fix.add_argument(
        "--all",
        action="store_true",
        help="Run all pre-commit checks, including slow ones.",
    )
    parser_fix.add_argument(
        "-w",
        "--working",
        action="store_true",
        help="Run on unstaged as well as staged changes.",
    )
    parser_fix.set_defaults(func=main_fix)
    add_no_color_flag(parser_fix)

    args, remaining = argparser.parse_known_args()
    if not hasattr(args, "func"):
        # If no subcommand was supplied, default to the 'check' command.
        parser_check.parse_args(namespace=args)

    configure_globals(args)
    chdir_to_git_root()
    args.func(args)


def add_no_color_flag(parser):
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Turn off colorized output.",
    )


def main_init(args):
    hookpath = os.path.join(".git", "hooks", "pre-commit")
    if not args.force and os.path.exists(hookpath):
        utils.error(f"{hookpath} already exists. Re-run with --force to overwrite it.")

    if not os.path.exists("precommit.py"):
        # Courtesy of https://setuptools.readthedocs.io/en/latest/pkg_resources.html
        template_path = pkg_resources.resource_filename(
            __name__, "precommit.py.template"
        )
        shutil.copyfile(template_path, "precommit.py")

    with open(hookpath, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\n\nprecommit --all\n")

    # Make the hook executable by everyone.
    st = os.stat(hookpath)
    os.chmod(hookpath, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main_fix(args):
    precommit = get_precommit(args)
    precommit.fix()


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


def configure_globals(args):
    """
    Configure global settings based on the command-line arguments.
    """
    # Check for the NO_COLOR environment variable and for a non-terminal standard output
    # before handling command-line arguments so that it can be overridden by explicitly
    # specifying --color.
    no_color = "NO_COLOR" in os.environ or not sys.stdout.isatty() or args.no_color
    if no_color:
        utils.turn_off_colors()

    utils.VERBOSE = args.verbose


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
            check_all=args.all,
            working=args.working,
        )
        return precommit
