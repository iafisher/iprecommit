import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

from . import lib


def main() -> None:
    argparser = argparse.ArgumentParser()
    subparsers = argparser.add_subparsers()

    lib._create_subparser(subparsers, "uninstall")

    argparser_template = lib._create_subparser(subparsers, "template")
    argparser_template.add_argument("--force", action="store_true", help="Overwrite existing precommit.py file.")

    argparser_install = lib._create_subparser(subparsers, "install")
    argparser_install.add_argument("--force", action="store_true", help="Overwrite existing pre-commit hook.")

    argparser_run = lib._create_subparser(subparsers, "run")
    lib._add_run_flags(argparser_run)

    argparser_fix = lib._create_subparser(subparsers, "fix")
    lib._add_fix_flags(argparser_fix)

    args = argparser.parse_args()
    try:
        _main(argparser, args)
    except lib.IPrecommitError as e:
        bail(str(e))


def _main(argparser, args) -> None:
    if args.subcmd == "template":
        main_template(args)
    elif args.subcmd == "install":
        main_install(args)
    elif args.subcmd == "run":
        run_precommit_py("run")
    elif args.subcmd == "fix":
        run_precommit_py("fix")
    elif args.subcmd == "uninstall":
        main_uninstall(args)
    else:
        argparser.print_usage()


PRECOMMIT_TEMPLATE = """\
from iprecommit import Precommit, checks

pre = Precommit()
pre.check(checks.NoDoNotSubmit())
pre.check(checks.NewlineAtEndOfFile())
# run a command:
#   pre.sh("./run_tests", "--verbose")
#   pre.sh("black", "--check", pass_files=True, base_pattern="*.py")
"""


# TODO: include some version information / comments
GIT_HOOK_TEMPLATE = """\
#!/bin/sh

set -e
%(prefix)s/bin/iprecommit run
"""


def main_template(args):
    change_to_git_root()

    p = Path("precommit.py")
    if p.exists():
        if args.force:
            warn("Overwriting existing precommit.py file.")
        else:
            bail("precommit.py already exists. Re-run with --force to overwrite.")

    # TODO: add option for custom path
    p.write_text(PRECOMMIT_TEMPLATE)
    


def main_install(args):
    change_to_git_root()

    py_prefix = Path(sys.prefix)
    try:
        py_prefix = py_prefix.relative_to(Path(".").absolute())
    except ValueError:
        pass

    # TODO: check if would overwrite
    p = Path(".git/hooks/pre-commit")
    if p.exists():
        if args.force:
            warn("Overwriting existing pre-commit hook.")
        else:
            bail("pre-commit hook already exists. Re-run with --force to overwrite.")

    p.write_text(GIT_HOOK_TEMPLATE % dict(prefix=py_prefix))
    perm = p.stat().st_mode
    p.chmod(perm | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main_uninstall(args):
    change_to_git_root()
    # TODO: error message if does not exist in the first place
    # TODO: check if installed by iprecommit
    os.remove(".git/hooks/pre-commit")


def run_precommit_py(subcmd: str) -> None:
    change_to_git_root()
    # TODO: less hacky way to do this?
    # TODO: what if sys.executable is None?
    proc = subprocess.run([sys.executable, "precommit.py", subcmd] + sys.argv[2:])
    sys.exit(proc.returncode)


def change_to_git_root() -> None:
    d = Path(".").absolute()
    while True:
        if (d / ".git").exists():
            os.chdir(d)
            return
        
        dn = d.parent
        if d == dn:
            raise lib.IPrecommitError("iprecommit must be run in a Git repository.")
        d = dn


def bail(msg: str) -> NoReturn:
    # TODO: color
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg: str) -> None:
    # TODO: color
    print(f"Warning: {msg}", file=sys.stderr)


if __name__ == "__main__":
    main()
