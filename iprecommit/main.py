import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Dict, NoReturn, Optional

from iprecommit.lib import red, yellow


def main() -> None:
    argparser = argparse.ArgumentParser(description="Manage Git pre-commit hooks.")
    subparsers = argparser.add_subparsers()

    argparser_fix = subparsers.add_parser("fix", help="Fix pre-commit failures.")
    argparser_fix.add_argument(
        "--unstaged", action="store_true", help="Fix failures in unstaged changes."
    )
    argparser_fix.set_defaults(func=main_fix)

    argparser_install = subparsers.add_parser(
        "install", help="Install the pre-commit hook in the Git repository."
    )
    argparser_install.add_argument(
        "--force", action="store_true", help="Overwrite an existing pre-commit hook"
    )
    argparser_install.add_argument(
        "--hook",
        default="hooks/precommit.py",
        help="Path to the hook script",
    )
    argparser_install.set_defaults(func=main_install)

    argparser_run = subparsers.add_parser(
        "run", help="Run the pre-commit checks manually."
    )
    argparser_run.add_argument(
        "--unstaged", action="store_true", help="Include unstaged changes."
    )
    argparser_run.set_defaults(func=main_run)

    argparser_uninstall = subparsers.add_parser(
        "uninstall", help="Uninstall the pre-commit hook from the Git repository."
    )
    argparser_uninstall.set_defaults(func=main_uninstall)

    args = argparser.parse_args()
    args.func(args)


def main_install(args) -> None:
    ensure_in_git_root()

    hookpath = normalize_hook_path(args.hook)
    if not hookpath.exists():
        bail(f"{hookpath} does not exist.")

    if not hookpath.stat().st_mode & stat.S_IXUSR:
        bail(f"{hookpath} is not an executable file.")

    git_hookpath = Path(".git") / "hooks" / "pre-commit"
    if git_hookpath.exists():
        if args.force:
            warn("Overwriting existing pre-commit hook.")
        else:
            bail("A pre-commit hook already exists. Re-run with --force to overwrite.")

    hookpath_string = (
        str(hookpath)
        if hookpath.is_absolute()
        else os.path.join("..", "..", str(hookpath))
    )
    result = subprocess.run(
        ["ln", "-s" + ("f" if args.force else ""), hookpath_string, git_hookpath],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        print(file=sys.stderr)
        bail("Failed to install the pre-commit hook.")


def main_run(args) -> None:
    if args.unstaged:
        env = dict(IPRECOMMIT_UNSTAGED="1")
    else:
        env = None

    run_with_env(env)


def main_fix(args) -> None:
    env = dict(IPRECOMMIT_FIX="1")
    if args.unstaged:
        env["IPRECOMMIT_UNSTAGED"] = "1"

    run_with_env(env)


def run_with_env(extended_env: Optional[Dict[str, str]]) -> None:
    ensure_in_git_root()

    git_hookpath = Path(".git") / "hooks" / "pre-commit"
    if not os.path.lexists(git_hookpath):
        bail("No pre-commit hook is installed. Run `iprecommit install` first.")

    if extended_env is not None:
        env = os.environ.copy()
        env.update(extended_env)
    else:
        env = None

    subprocess.run(git_hookpath, env=env)


def main_uninstall(_args) -> None:
    ensure_in_git_root()

    git_hookpath = Path(".git") / "hooks" / "pre-commit"
    if not os.path.lexists(git_hookpath):
        bail("There is no existing pre-commit hook to uninstall.")

    result = subprocess.run(
        ["rm", git_hookpath], stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        print(file=sys.stderr)
        bail("Failed to uninstall the pre-commit hook.")


def ensure_in_git_root() -> None:
    # TODO(2024-08-15): loosen this requirement to just being in the git repo
    if not Path(".git").exists():
        bail("You must be in the root of a Git repository.")


def normalize_hook_path(pathstr: str) -> Path:
    repository_path = Path(".").absolute()
    user_path = Path(pathstr).absolute()

    if user_path.is_relative_to(repository_path):
        return user_path.relative_to(repository_path)
    else:
        return user_path


def bail(msg: str) -> NoReturn:
    print(f"{red('Error:')} {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg: str) -> None:
    print(f"{yellow('Warning:')} {msg}")


if __name__ == "__main__":
    main()
