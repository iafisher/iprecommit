import argparse
import importlib.metadata
import os
import shutil
import stat
import sys
import uuid
from pathlib import Path

from . import lib


def main() -> None:
    argparser = argparse.ArgumentParser(
        description="Dead-simple Git pre-commit hook management."
    )
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

    argparser_run = _create_subparser(
        subparsers, "run", help="Manually run the pre-commit hook."
    )
    add_config_file_arg(argparser_run)
    add_unstaged_and_all_flags(argparser_run)

    argparser_fix = _create_subparser(
        subparsers, "fix", help="Apply fixes to failing checks."
    )
    add_config_file_arg(argparser_fix)
    add_unstaged_and_all_flags(argparser_fix)

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
    except lib.IPrecommitError as e:
        lib.bail(str(e))


def _main(argparser, args) -> None:
    if args.subcmd == "install":
        main_install(args)
    elif args.subcmd == "run":
        main_pre_commit(args)
    elif args.subcmd == "fix":
        main_fix(args)
    elif args.subcmd == "run-commit-msg":
        main_commit_msg(args)
    elif args.subcmd == "run-pre-push":
        main_pre_push(args)
    elif args.subcmd == "uninstall":
        main_uninstall(args)
    else:
        argparser.print_usage()


def main_pre_commit(args):
    change_to_git_root()

    config = lib.parse_config_toml(args.config)
    checks = lib.Checks(config)
    checks.run_pre_commit(fix_mode=False, unstaged=args.unstaged, all_files=args.all)


def main_fix(args):
    change_to_git_root()

    config = lib.parse_config_toml(args.config)
    checks = lib.Checks(config)
    checks.run_pre_commit(fix_mode=True, unstaged=args.unstaged, all_files=args.all)


def main_commit_msg(args):
    change_to_git_root()

    config = lib.parse_config_toml(args.config)
    checks = lib.Checks(config)
    checks.run_commit_msg(args.commit_msg)


def main_pre_push(args):
    change_to_git_root()

    config = lib.parse_config_toml(args.config)
    checks = lib.Checks(config)
    checks.run_pre_push(args.remote)


ENV_TOML_TEMPLATE = "IPRECOMMIT_TOML_TEMPLATE"


def main_install(args):
    change_to_git_root()

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
    if not precommit_path.exists():
        write_template = lambda: precommit_path.write_text(PRECOMMIT_TEMPLATE)

        custom_template_path = os.environ.get(ENV_TOML_TEMPLATE)
        if custom_template_path is not None:
            try:
                shutil.copyfile(custom_template_path, precommit_path)
            except FileNotFoundError:
                lib.warn(
                    f"File at {ENV_TOML_TEMPLATE} ({custom_template_path}) does not exist. Falling back to default template."
                )
                write_template()
            except OSError:
                lib.warn(
                    f"Failed to copy from {ENV_TOML_TEMPLATE} ({custom_template_path}). Falling back to default template."
                )
                write_template()
        else:
            write_template()

    py_prefix = Path(sys.prefix)
    try:
        py_prefix = py_prefix.relative_to(Path(".").absolute())
    except ValueError:
        pass

    if args.path:
        extra_args = f" --config {args.path}"
    else:
        extra_args = ""

    _write_script(
        pre_commit_hook_path,
        GIT_PRE_COMMIT_HOOK_TEMPLATE,
        py_prefix=py_prefix,
        extra_args=extra_args,
    )
    _write_script(
        commit_msg_hook_path,
        GIT_COMMIT_MSG_HOOK_TEMPLATE,
        py_prefix=py_prefix,
        extra_args=extra_args,
    )
    _write_script(
        pre_push_hook_path,
        GIT_PRE_PUSH_HOOK_TEMPLATE,
        py_prefix=py_prefix,
        extra_args=extra_args,
    )


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

[[pre_commit]]
name = "NoForbiddenStrings"
cmd = ["iprecommit-no-forbidden-strings", "--paths"]

[[pre_commit]]
name = "NewlineAtEndOfFile"
cmd = ["iprecommit-newline-at-eof"]

# [[pre_commit]]
# name = "PythonFormat"
# cmd = ["black", "--check"]
# filters = ["*.py"]
# fix_cmd = ["black"]

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


GIT_PRE_COMMIT_HOOK_TEMPLATE = """\
#!/bin/sh

# generated by iprecommit, version %(version)s

set -e
%(prefix)s/bin/iprecommit run%(extra_args)s
"""


GIT_COMMIT_MSG_HOOK_TEMPLATE = """\
#!/bin/sh

# generated by iprecommit, version %(version)s

set -e

%(prefix)s/bin/iprecommit run-commit-msg --commit-msg "$1"%(extra_args)s
"""


GIT_PRE_PUSH_HOOK_TEMPLATE = """\
#!/bin/sh

# generated by iprecommit, version %(version)s

set -e

%(prefix)s/bin/iprecommit run-pre-push --remote "$1"%(extra_args)s
"""


def _write_script(path: Path, text: str, *, py_prefix: Path, extra_args: str) -> None:
    replace_file(
        path,
        text % dict(prefix=py_prefix, version=get_version(), extra_args=extra_args),
    )
    perm = path.stat().st_mode
    path.chmod(perm | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _check_overwrite(path: Path, *, force: bool) -> None:
    if path.exists():
        if force:
            lib.warn(f"Overwriting existing hook at {path}.")
        else:
            lib.bail(f"{path} already exists. Re-run with --force to overwrite.")


def main_uninstall(args):
    change_to_git_root()
    p = Path(".git/hooks/pre-commit")
    if not p.exists():
        lib.bail("No pre-commit hook exists.")

    if "generated by iprecommit" not in p.read_text():
        if args.force:
            lib.warn("Uninstalling existing pre-commit hook.")
        else:
            lib.bail(
                "Existing pre-commit hook is not from iprecommit. Re-run with --force to uninstall anyway."
            )

    os.remove(p)


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


def get_version():
    return importlib.metadata.version("iprecommit")


def _create_subparser(subparsers, name, *, help):
    argparser = subparsers.add_parser(name, description=help, help=help)
    argparser.set_defaults(subcmd=name)
    return argparser


if __name__ == "__main__":
    main()
