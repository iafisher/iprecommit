import argparse
import importlib.metadata
import os
import shutil
import stat
import subprocess
import sys
import uuid
from pathlib import Path

from . import tomlconfig
from .checks import Checks
from .common import IPrecommitError, bail, warn


def main() -> None:
    argparser = argparse.ArgumentParser(
        description="Dead-simple Git pre-commit hook management."
    )
    argparser.add_argument("--version", action="version", version=get_version())
    subparsers = argparser.add_subparsers(title="subcommands", metavar="")

    argparser_install = _create_subparser(
        subparsers,
        "install",
        help="Install an iprecommit hook in the current Git repository.",
    )
    argparser_install.add_argument(
        "--force", action="store_true", help="Overwrite existing pre-commit hook."
    )
    argparser_install.add_argument(
        "--path", help="Customize configuration file path. [default: precommit.toml]"
    )

    argparser_uninstall = _create_subparser(
        subparsers,
        "uninstall",
        help="Uninstall the iprecommit hook in the current Git repository.",
    )
    argparser_uninstall.add_argument(
        "--force", action="store_true", help="Uninstall a non-iprecommit hook."
    )

    def add_config_file_arg(argparser):
        default = "precommit.toml"
        argparser.add_argument(
            "--config",
            default=default,
            help=f"Custom path to TOML configuration file. [default: {default}]",
        )

    def add_unstaged_and_all_flags(argparser):
        group = argparser.add_mutually_exclusive_group()
        group.add_argument(
            "--unstaged", action="store_true", help="Also run on unstaged files."
        )
        group.add_argument(
            "--all", action="store_true", help="Run on all files in the repository."
        )

    def add_skip_flag(argparser):
        argparser.add_argument(
            "--skip",
            action="append",
            metavar="CHECK",
            default=[],
            help="Skip the given check (repeatable).",
        )

    def add_only_flag(argparser):
        argparser.add_argument(
            "--only",
            action="append",
            metavar="CHECK",
            default=[],
            help="Run only the given check (repeatable).",
        )

    argparser_run = _create_subparser(
        subparsers, "run", help="Manually run the pre-commit hook."
    )
    add_config_file_arg(argparser_run)
    add_unstaged_and_all_flags(argparser_run)
    argparser_run.add_argument(
        "--fail-fast", action="store_true", help="Stop at the first failing check."
    )
    add_skip_flag(argparser_run)
    add_only_flag(argparser_run)

    argparser_fix = _create_subparser(
        subparsers, "fix", help="Apply fixes to failing checks."
    )
    add_config_file_arg(argparser_fix)
    add_unstaged_and_all_flags(argparser_fix)
    add_skip_flag(argparser_fix)
    add_only_flag(argparser_fix)

    argparser_run_commit_msg = _create_subparser(
        subparsers, "run-commit-msg", help="Manually run the commit-msg hook."
    )
    argparser_run_commit_msg.add_argument(
        "--commit-msg", help="Path to commit message file."
    )
    add_config_file_arg(argparser_run_commit_msg)

    argparser_run_pre_push = _create_subparser(
        subparsers, "run-pre-push", help="Manually run the pre-push hook."
    )
    argparser_run_pre_push.add_argument("--remote")
    add_config_file_arg(argparser_run_pre_push)

    args = argparser.parse_args()
    try:
        _main(argparser, args)
    except IPrecommitError as e:
        bail(str(e))


def _main(argparser, args) -> None:
    git_root = find_git_root()

    if in_debug_mode():
        print_debugging_info(args, git_root)

    subcmd = getattr(args, "subcmd", "")
    if subcmd == "install":
        main_install(args, git_root)
    elif subcmd == "run":
        main_pre_commit(args, git_root)
    elif subcmd == "fix":
        main_fix(args, git_root)
    elif subcmd == "run-commit-msg":
        main_commit_msg(args, git_root)
    elif subcmd == "run-pre-push":
        main_pre_push(args, git_root)
    elif subcmd == "uninstall":
        main_uninstall(args, git_root)
    else:
        argparser.print_help()


def main_pre_commit(args, git_root: Path) -> None:
    os.chdir(git_root)

    config = tomlconfig.parse(args.config)
    checks = Checks(config)
    checks.run_pre_commit(
        fix_mode=False,
        unstaged=args.unstaged,
        all_files=args.all,
        fail_fast=args.fail_fast,
        skip=args.skip,
        only=args.only,
    )


def in_debug_mode():
    v = os.environ.get("IPRECOMMIT_DEBUG")
    return v is not None and v != "0"


def print_debugging_info(args, git_root) -> None:
    print_err = lambda *args, **kwargs: print(*args, file=sys.stderr, **kwargs)

    try:
        print_err("debug: iprecommit version:", get_version())
    except Exception as e:
        print_err("debug: failed to get iprecommit version:", e)

    try:
        print_err("debug: git version:", get_git_version())
    except Exception as e:
        print_err("debug: failed to get git version:", e)

    try:
        git_config = get_git_config()
    except Exception as e:
        print_err("debug: failed to get git config:", e)
    else:
        for key, value in git_config:
            if key.startswith("core."):
                print_err(f"debug: git config: {key}={value}")

    print_err("debug: env: PATH=" + os.environ.get("PATH", ""))

    for key, val in os.environ.items():
        if key.startswith("GIT_"):
            print_err(f"debug: env: {key}={val}")

    print_err("debug: git root:", git_root)

    for key, val in vars(args).items():
        print_err(f"debug: arg: {key}={val}")


def main_fix(args, git_root: Path) -> None:
    os.chdir(git_root)

    config = tomlconfig.parse(args.config)
    checks = Checks(config)
    checks.run_pre_commit(
        fix_mode=True,
        unstaged=args.unstaged,
        all_files=args.all,
        skip=args.skip,
        only=args.only,
    )


def main_commit_msg(args, git_root: Path) -> None:
    os.chdir(git_root)

    config = tomlconfig.parse(args.config)
    checks = Checks(config)
    checks.run_commit_msg(Path(args.commit_msg))


def main_pre_push(args, git_root: Path) -> None:
    os.chdir(git_root)

    config = tomlconfig.parse(args.config)
    checks = Checks(config)
    checks.run_pre_push(args.remote)


ENV_TOML_TEMPLATE = "IPRECOMMIT_TOML_TEMPLATE"


def main_install(args, git_root: Path) -> None:
    os.chdir(git_root)

    # check this early so that we bail before make other changes like creating precommit.toml
    pre_commit_hook_path = Path(".git/hooks/pre-commit")
    _check_overwrite(pre_commit_hook_path, force=args.force)
    commit_msg_hook_path = Path(".git/hooks/commit-msg")
    _check_overwrite(commit_msg_hook_path, force=args.force)
    pre_push_hook_path = Path(".git/hooks/pre-push")
    _check_overwrite(pre_push_hook_path, force=args.force)

    precommit_path = (
        Path(args.path) if args.path is not None else Path("precommit.toml")
    )
    did_i_write_precommit_file = False
    if not precommit_path.exists():
        write_template = lambda: precommit_path.write_text(PRECOMMIT_TEMPLATE)

        custom_template_path = os.environ.get(ENV_TOML_TEMPLATE)
        if custom_template_path is not None:
            try:
                shutil.copyfile(custom_template_path, precommit_path)
            except FileNotFoundError:
                warn(
                    f"File at {ENV_TOML_TEMPLATE} ({custom_template_path}) does not exist. Falling back to default template."
                )
                write_template()
            except OSError:
                warn(
                    f"Failed to copy from {ENV_TOML_TEMPLATE} ({custom_template_path}). Falling back to default template."
                )
                write_template()
        else:
            write_template()

        did_i_write_precommit_file = True

    git_root = Path(".").absolute()
    iprecommit_path = get_iprecommit_path(git_root)

    if args.path:
        extra_args = f" --config {args.path}"
    else:
        extra_args = ""

    # The pre-commit check may be invoked in an environment with a restricted `PATH`, e.g. from a
    # Git GUI program. `get_iprecommit_path` handles finding the path to the `iprecommit` program
    # itself, but we still need to be able to find the default checks, like
    # `iprecommit-no-forbidden-strings`. We try to do so here and add its directory to the `PATH`
    # used by the pre-commit check.
    #
    # https://github.com/iafisher/iprecommit/issues/72
    iprecommit_extras_path = shutil.which("iprecommit-no-forbidden-strings")
    if iprecommit_extras_path is not None:
        iprecommit_extras_dir = os.path.split(iprecommit_extras_path)[0]
        export_path = f'export PATH="$PATH:{iprecommit_extras_dir}"'
    else:
        export_path = ""

    _write_script(
        pre_commit_hook_path,
        GIT_HOOK_TEMPLATE,
        iprecommit_path=iprecommit_path,
        args="run" + extra_args,
        export_path=export_path,
    )
    print(f"Created hook: {pre_commit_hook_path}")
    _write_script(
        commit_msg_hook_path,
        GIT_HOOK_TEMPLATE,
        iprecommit_path=iprecommit_path,
        args='run-commit-msg --commit-msg "$1"' + extra_args,
        export_path=export_path,
    )
    print(f"Created hook: {commit_msg_hook_path}")
    _write_script(
        pre_push_hook_path,
        GIT_HOOK_TEMPLATE,
        iprecommit_path=iprecommit_path,
        args='run-pre-push --remote "$1"' + extra_args,
        export_path=export_path,
    )
    print(f"Created hook: {pre_push_hook_path}")

    if did_i_write_precommit_file:
        print()
        print("Created precommit.toml from template. Edit it to add your own checks.")


def get_iprecommit_path(git_root: Path) -> str:
    # Why not just put unqualified 'iprecommit' in the hook file?
    #
    #   - If 'iprecommit' isn't on PATH, then that won't work.
    #   - If 'iprecommit' is in virtual environment, then we should always use the virtual
    #     environment version, even if 'git commit' is invoked without the virtual environment
    #     activated.
    #
    # In short, we should do our best to use the same 'iprecommit' executable that
    # 'iprecommit install' was invoked as.

    # Special case: 'iprecommit' was invoked with a pathname instead of as a bare command.
    if "/" in sys.argv[0]:
        p = Path(sys.argv[0]).absolute()
        if p.is_relative_to(git_root):
            # Common case: 'iprecommit' is in a virtual environment inside the Git root folder.
            # We should make a relative path so the repository folder can be moved without
            # breaking the path.
            return str(p.relative_to(git_root))
        else:
            return str(p)
    else:
        # Otherwise, try to find where the executable lives, falling back on the current
        # directory.
        #
        # That's probably not a good guess, but it doesn't have to be perfect since the hook script
        # template has fallback logic in case the path returned here doesn't work.
        return shutil.which("iprecommit") or str(Path(sys.argv[0]).absolute())


def replace_file(path: Path, new_contents: str) -> None:
    # Writing to a tempfile and then moving to `path` ensures 3 things:
    #
    #  (1) Anyone currently reading from `path` won't see a mix of old and new contents.
    #  (2) Since `rename` is atomic (at least, on Linux and macOS), there is no interval where
    #      `path` does not exist.
    #  (3) If `path` is a symlink, the symlink will be replaced by a normal file, instead of
    #      following the symlink and writing to some random file elsewhere.
    #
    tempfile = path.parent / f"iprecommit-tempfile-{uuid.uuid4()}"
    tempfile.write_text(new_contents)
    os.rename(tempfile, path)


PRECOMMIT_TEMPLATE = """\
# This file configures Git hooks for the project.
# Documentation: https://github.com/iafisher/iprecommit

# Set 'fail_fast' to 'true' to abort the run after the first failing check.
# You can also set 'fail_fast' on individual checks.
fail_fast = false

[[pre_commit]]
name = "NoForbiddenStrings"
cmd = ["iprecommit-no-forbidden-strings", "--paths"]

[[pre_commit]]
name = "NewlineAtEndOfFile"
cmd = ["iprecommit-newline-at-eof"]
fix_cmd = ["iprecommit-newline-at-eof", "--fix"]
# Uncomment the next two lines to have this check auto-fix and retry immediately on failure.
# autofix = true
# fail_fast = true

# [[pre_commit]]
# name = "PythonFormat"
# cmd = ["black", "--check"]
# filters = ["*.py"]
# fix_cmd = ["black"]
# autofix = true
# fail_fast = true

# [[pre_commit]]
# name = "ProjectTests"
# cmd = ["./run_tests"]
# pass_files = false

# commit-msg checks
[[commit_msg]]
name = "CommitMessageFormat"
cmd = ["iprecommit-commit-msg-format", "--max-line-length", "72"]

# pre-push checks (run on commit messages)
[[pre_push]]
name = "NoForbiddenStrings"
cmd = ["iprecommit-no-forbidden-strings", "--commits"]
"""


GIT_HOOK_TEMPLATE = """\
#!/bin/sh

# generated by iprecommit, version %(version)s

set -e

%(export_path)s

if [ -x "%(iprecommit_path)s" ]; then
  "%(iprecommit_path)s" %(args)s
elif command -v iprecommit >/dev/null 2>&1; then
  iprecommit %(args)s
else
  echo "ERROR: You have a pre-commit script at .git/hooks/pre-commit created by"
  echo "iprecommit (https://github.com/iafisher/iprecommit), but the 'iprecommit'"
  echo "executable could not be found."
  echo
  echo "To fix this:"
  echo
  echo "  pip install iprecommit"
  echo "  iprecommit install --force"
  echo
  echo "Or you can delete .git/hooks/pre-commit if you don't want to use iprecommit."
  exit 1
fi
"""


def _write_script(
    path: Path, text: str, *, iprecommit_path: str, args: str, export_path: str
) -> None:
    replace_file(
        path,
        text
        % dict(
            iprecommit_path=iprecommit_path,
            version=get_version(),
            args=args,
            export_path=export_path,
        ),
    )
    perm = path.stat().st_mode
    path.chmod(perm | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _check_overwrite(path: Path, *, force: bool) -> None:
    if path.exists():
        if force:
            warn(f"Overwriting existing hook at {path}.")
        else:
            bail(f"{path} already exists. Re-run with --force to overwrite.")


def main_uninstall(args, git_root: Path) -> None:
    os.chdir(git_root)

    p = Path(".git/hooks/pre-commit")
    if not p.exists():
        bail("No pre-commit hook exists.")

    if "generated by iprecommit" not in p.read_text():
        if args.force:
            warn("Uninstalling existing pre-commit hook.")
        else:
            bail(
                "Existing pre-commit hook is not from iprecommit. Re-run with --force to uninstall anyway."
            )

    os.remove(p)


def find_git_root() -> Path:
    d = Path(".").absolute()
    while True:
        if (d / ".git").exists():
            return d

        dn = d.parent
        if d == dn:
            raise IPrecommitError("iprecommit must be run in a Git repository.")
        d = dn


def get_git_version():
    return subprocess.run(
        ["git", "--version"], check=True, text=True, capture_output=True
    ).stdout.strip()


def get_git_config():
    stdout = subprocess.run(
        ["git", "config", "--list"], check=True, text=True, capture_output=True
    ).stdout
    return [line.split("=", maxsplit=1) for line in stdout.splitlines()]


def get_version():
    return importlib.metadata.version("iprecommit")


def _create_subparser(subparsers, name, *, help):
    argparser = subparsers.add_parser(name, description=help, help=help)
    argparser.set_defaults(subcmd=name)
    return argparser


if __name__ == "__main__":
    main()
