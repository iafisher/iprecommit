import argparse
import importlib.metadata
import os
import stat
import subprocess
import sys
from pathlib import Path

from . import lib


def main() -> None:
    argparser = argparse.ArgumentParser(
        description="Dead-simple Git pre-commit hook management."
    )
    subparsers = argparser.add_subparsers(title="subcommands", metavar="")

    argparser_init = _create_subparser(
        subparsers,
        "install",
        help="Install an iprecommit hook in the current Git repository.",
    )
    argparser_init.add_argument(
        "--force", action="store_true", help="Overwrite existing pre-commit hook."
    )
    argparser_init.add_argument(
        "--path", help="Create precommit.py in a custom location."
    )

    argparser_uninstall = _create_subparser(
        subparsers,
        "uninstall",
        help="Uninstall the iprecommit hook in the current Git repository.",
    )
    argparser_uninstall.add_argument(
        "--force", action="store_true", help="Uninstall a non-iprecommit hook."
    )

    argparser_run = _create_subparser(
        subparsers, "run", help="Manually run the iprecommit hook."
    )
    argparser_run.add_argument(
        "--unstaged", action="store_true", help="Also run checks on unstaged files."
    )
    argparser_run.add_argument("--hook", default="pre-commit")
    argparser_run.add_argument("--commit-msg", help=argparse.SUPPRESS)
    argparser_run.add_argument("--remote", help=argparse.SUPPRESS)

    argparser_fix = _create_subparser(
        subparsers, "fix", help="Apply fixes to failing checks."
    )
    argparser_fix.add_argument(
        "--unstaged", action="store_true", help="Also apply fixes to unstaged files."
    )
    argparser_fix.add_argument("--hook", default="pre-commit")

    args = argparser.parse_args()
    try:
        _main(argparser, args)
    except lib.IPrecommitError as e:
        lib.bail(str(e))


def _main(argparser, args) -> None:
    if args.subcmd == "install":
        main_install(args)
    elif args.subcmd == "run":
        run_precommit_py(args)
    elif args.subcmd == "fix":
        run_precommit_py(args)
    elif args.subcmd == "uninstall":
        main_uninstall(args)
    else:
        argparser.print_usage()


# TODO: example of include/exclude patterns
PRECOMMIT_TEMPLATE = """\
from iprecommit import Pre, checks

pre = Pre()
pre.commit.check(checks.NoDoNotCommit())
pre.commit.check(checks.NewlineAtEndOfFile())
# run a command:
#   pre.commit.sh("./run_tests", "--verbose")
#   pre.commit.sh("black", "--check", pass_files=True, base_pattern="*.py")

# commit-msg checks
pre.commit_msg.check(checks.CommitMessageFormat(max_length=72))

pre.main()
"""


GIT_PRE_COMMIT_HOOK_TEMPLATE = """\
#!/bin/sh

# generated by iprecommit, version %(version)s

set -e
%(path_env)s
%(prefix)s/bin/iprecommit run
"""


GIT_COMMIT_MSG_HOOK_TEMPLATE = """\
#!/bin/sh

# generated by iprecommit, version %(version)s

set -e
%(path_env)s
%(prefix)s/bin/iprecommit run --hook commit-msg --commit-msg "$1"
"""


GIT_PRE_PUSH_HOOK_TEMPLATE = """\
#!/bin/sh

# generated by iprecommit, version %(version)s

set -e
%(path_env)s
%(prefix)s/bin/iprecommit run --hook pre-push --remote "$1"
"""


def main_install(args):
    change_to_git_root()

    # check this early so that we bail before make other changes like creating precommit.py
    pre_commit_hook_path = Path(".git/hooks/pre-commit")
    _check_overwrite(pre_commit_hook_path, force=args.force)
    commit_msg_hook_path = Path(".git/hooks/commit-msg")
    _check_overwrite(commit_msg_hook_path, force=args.force)
    pre_push_hook_path = Path(".git/hooks/pre-push")
    _check_overwrite(pre_push_hook_path, force=args.force)

    precommit_path = Path(args.path) if args.path is not None else Path("precommit.py")
    if not precommit_path.exists():
        precommit_path.write_text(PRECOMMIT_TEMPLATE)

    py_prefix = Path(sys.prefix)
    try:
        py_prefix = py_prefix.relative_to(Path(".").absolute())
    except ValueError:
        pass

    if args.path:
        path_env = f"export {lib.ENV_HOOK_PATH}={args.path}"
    else:
        path_env = ""

    _write_script(
        pre_commit_hook_path,
        GIT_PRE_COMMIT_HOOK_TEMPLATE,
        py_prefix=py_prefix,
        path_env=path_env,
    )
    _write_script(
        commit_msg_hook_path,
        GIT_COMMIT_MSG_HOOK_TEMPLATE,
        py_prefix=py_prefix,
        path_env=path_env,
    )
    _write_script(
        pre_push_hook_path,
        GIT_PRE_PUSH_HOOK_TEMPLATE,
        py_prefix=py_prefix,
        path_env=path_env,
    )


def _write_script(path: Path, text: str, *, py_prefix: Path, path_env: str) -> None:
    path.write_text(
        text % dict(prefix=py_prefix, version=get_version(), path_env=path_env)
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


# `hook` is the Git hook, e.g. "pre-commit" or "commit-msg"
def run_precommit_py(args) -> None:
    commit_msg = getattr(args, "commit_msg", None)
    if commit_msg is not None and args.hook != "commit-msg":
        lib.bail(
            "The --commit-msg flag is only valid when --hook is set to 'commit-msg'."
        )

    remote = getattr(args, "remote", None)
    if remote is not None and args.hook != "pre-push":
        lib.bail("The --remote flag is only valid when --hook is set to 'pre-push'.")

    precommit_args = lib.CLIArgs(
        hook_name=args.hook,
        unstaged=args.unstaged,
        fix_mode=(args.subcmd == "fix"),
        commit_msg=commit_msg,
        remote=remote,
    )

    # `iprecommit run ...` becomes `python precommit.py pre-commit ...`
    change_to_git_root()
    path = os.environ.get(lib.ENV_HOOK_PATH, "precommit.py")
    # TODO: less hacky way to do this?
    # TODO: what if sys.executable is None?
    proc = subprocess.run([sys.executable, path] + precommit_args.serialize())
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


def get_version():
    return importlib.metadata.version("iprecommit")


def _create_subparser(subparsers, name, *, help):
    argparser = subparsers.add_parser(name, description=help, help=help)
    argparser.set_defaults(subcmd=name)
    return argparser


if __name__ == "__main__":
    main()
