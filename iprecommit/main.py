import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Dict, NoReturn, Optional, Tuple

from iprecommit.lib import red, warn


DEFAULT_HOOK_PATH = "hooks/precommit.py"


def main() -> None:
    argparser = argparse.ArgumentParser(description="Manage Git pre-commit hooks.")
    subparsers = argparser.add_subparsers(metavar="subcommand")

    argparser_fix = subparsers.add_parser("fix", help="Fix pre-commit failures.")
    argparser_fix.add_argument(
        "--staged", action="store_true", help="Only fix failures in staged changes."
    )
    argparser_fix.set_defaults(func=main_fix)

    argparser_init = subparsers.add_parser(
        "init", help="Initialize a new pre-commit hook."
    )
    argparser_init.add_argument(
        "--hook", default=DEFAULT_HOOK_PATH, help="Where to create the hook script"
    )
    argparser_init.add_argument(
        "--force", action="store_true", help="Overwrite an existing pre-commit hook"
    )
    argparser_init.set_defaults(func=main_init)

    argparser_install = subparsers.add_parser(
        "install", help="Install the pre-commit hook in the Git repository."
    )
    argparser_install.add_argument(
        "--force", action="store_true", help="Overwrite an existing pre-commit hook"
    )
    argparser_install.add_argument(
        "--hook",
        default=DEFAULT_HOOK_PATH,
        help="Path to the hook script",
    )
    argparser_install.set_defaults(func=main_install)

    argparser_run = subparsers.add_parser(
        "run", help="Run the pre-commit checks manually."
    )
    argparser_run.add_argument(
        "--staged", action="store_true", help="Only check staged changes."
    )
    argparser_run.set_defaults(func=main_run)

    argparser_uninstall = subparsers.add_parser(
        "uninstall", help="Uninstall the pre-commit hook from the Git repository."
    )
    argparser_uninstall.set_defaults(func=main_uninstall)

    args = argparser.parse_args()
    args.func(args)


PRECOMMIT_TEMPLATE = """\
#!/usr/bin/env python
from iprecommit import Precommit, checks

pre = Precommit()
pre.check(checks.NoDoNotSubmit())
pre.check(checks.NewlineAtEndOfFile())
# run a command:
#   pre.command(["black", "--check"], pass_files=True, pattern="*.py")
"""


def main_init(args) -> None:
    ensure_in_git_root()
    path_to_git_hook, path_to_script = check_paths(
        args.hook, force=args.force, script_must_exist=True
    )

    if path_to_script.exists():
        if args.force:
            warn(f"Overwriting existing file at {path_to_script}.")
        else:
            bail(
                f"{path_to_script} already exists.\n\n"
                + "Re-run with `--force` to replace with a template, or run `install` to install existing hook."
            )

    path_to_script.parent.mkdir(parents=True, exist_ok=True)
    path_to_script.write_text(PRECOMMIT_TEMPLATE)
    stat_result = path_to_script.stat()
    path_to_script.chmod(stat_result.st_mode | stat.S_IXUSR)

    create_symlink(path_to_git_hook, path_to_script, force=args.force)


def main_install(args) -> None:
    ensure_in_git_root()
    path_to_git_hook, path_to_script = check_paths(
        args.hook, force=args.force, script_must_exist=True
    )
    create_symlink(path_to_git_hook, path_to_script, force=args.force)


# returns (path to git hook, path to script)
def check_paths(
    pathstr_to_script: str, *, force: bool, script_must_exist: bool
) -> Tuple[Path, Path]:
    path_to_git_hook = Path(".git") / "hooks" / "pre-commit"
    check_path_to_git_hook(path_to_git_hook, force=force)

    path_to_script = normalize_path_to_script(pathstr_to_script)
    if script_must_exist:
        check_path_to_script(path_to_script)

    return path_to_git_hook, path_to_script


def create_symlink(
    path_to_git_hook: Path, path_to_script: Path, *, force: bool
) -> None:
    hookpath_string = (
        str(path_to_script)
        if path_to_script.is_absolute()
        else os.path.join("..", "..", str(path_to_script))
    )
    result = subprocess.run(
        ["ln", "-s" + ("f" if force else ""), hookpath_string, path_to_git_hook],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        print(file=sys.stderr)
        bail("Failed to install the pre-commit hook.")


def check_path_to_script(hookpath: Path) -> None:
    if not hookpath.exists():
        bail(f"{hookpath} does not exist.")

    if not hookpath.stat().st_mode & stat.S_IXUSR:
        bail(f"{hookpath} is not an executable file.")


def check_path_to_git_hook(git_hookpath: Path, *, force: bool) -> None:
    if git_hookpath.exists():
        if force:
            warn("Overwriting existing pre-commit hook.")
        else:
            bail("A pre-commit hook already exists. Re-run with --force to overwrite.")


def main_run(args) -> None:
    if args.staged:
        env = None
    else:
        env = dict(IPRECOMMIT_UNSTAGED="1")

    run_with_env(env)


def main_fix(args) -> None:
    env = dict(IPRECOMMIT_FIX="1")
    if not args.staged:
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


def normalize_path_to_script(pathstr: str) -> Path:
    repository_path = Path(".").absolute()
    user_path = Path(pathstr).absolute()

    if user_path.is_relative_to(repository_path):
        return user_path.relative_to(repository_path)
    else:
        return user_path


def bail(msg: str) -> NoReturn:
    print(f"{red('Error:')} {msg}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
