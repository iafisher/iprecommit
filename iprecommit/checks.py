import contextlib
import fnmatch
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, NoReturn, Tuple, Union

from . import githelper, tomlconfig
from .common import IPrecommitError, cyan, green, red, yellow
from .tomlconfig import CommitMsgCheck, PreCommitCheck, PrePushCheck


class Checks:
    num_failed_checks: int
    failed_fixable_checks: List[PreCommitCheck]
    config: tomlconfig.Config

    def __init__(self, config: tomlconfig.Config) -> None:
        self.num_failed_checks = 0
        self.failed_fixable_checks = []
        self.config = config

    def run_pre_commit(
        self,
        *,
        fix_mode: bool,
        unstaged: bool,
        all_files: bool,
        fail_fast: bool = False,
        skip: List[str],
        only: List[str],
    ) -> None:
        assert not (unstaged and all_files)

        skip_from_envvar = _parse_skip_envvar()
        checks = self._get_checks_to_run(
            only_list=only, skip_list=skip + skip_from_envvar
        )

        if all_files:
            all_changed_paths = list(
                sorted(
                    set(
                        githelper.get_tracked_files()
                        + githelper.get_changed_paths(include_unstaged=True)
                        + githelper.get_untracked_files()
                    )
                    - set(githelper.get_deleted_paths(include_unstaged=True))
                )
            )

            if len(all_changed_paths) == 0:
                print("iprecommit: The repository is empty. Add some files and re-run.")
                sys.exit(1)
        elif unstaged:
            all_changed_paths = githelper.get_changed_paths(include_unstaged=True) + (
                githelper.get_untracked_files()
            )

            if len(all_changed_paths) == 0:
                print(
                    "iprecommit: No files are changed (staged or unstaged) in Git. "
                    + "Change some files, or re-run iprecommit with --all."
                )
                sys.exit(1)
        else:
            all_changed_paths = githelper.get_changed_paths(include_unstaged=False)
            # We check this condition instead of `len(all_changed_paths) == 0` because deleted
            # files won't show up in `all_changed_paths` even though they are staged changes.
            #
            # https://github.com/iafisher/iprecommit/issues/73
            if not githelper.any_staged_changes():
                print(
                    "iprecommit: No files are staged in Git. "
                    + "Stage some files, or re-run iprecommit with --unstaged or --all."
                )
                sys.exit(1)

        if fix_mode:
            self._run_pre_commit_fix(
                all_changed_paths, checks=checks, unstaged=unstaged
            )
        else:
            self._run_pre_commit_check(
                all_changed_paths, checks=checks, fail_fast=fail_fast
            )

            if self.num_failed_checks > 0 and len(self.failed_fixable_checks) > 0:
                print()
                print()
                self._print_block_status("attempting autofix")
                self._run_pre_commit_fix(
                    all_changed_paths,
                    checks=self.failed_fixable_checks,
                    unstaged=unstaged,
                )

                self.num_failed_checks = 0
                self.failed_fixable_checks.clear()
                print()
                print()
                self._print_block_status("retrying after autofix")
                self._run_pre_commit_check(
                    all_changed_paths, checks=checks, fail_fast=fail_fast
                )

        self._summary("Commit")

    def _run_pre_commit_check(
        self,
        all_changed_paths: List[Path],
        *,
        checks: List[PreCommitCheck],
        fail_fast: bool,
    ) -> None:
        for i, check in enumerate(checks):
            filtered_changed_paths = filter_paths(all_changed_paths, check.filters)
            if check.skip or not filtered_changed_paths:
                self._print_status(check.name, yellow("skipped"))
                print()
                continue

            self._print_status(check.name, "running")
            cmd = check.cmd
            # TODO: test where pass_files=False
            if check.pass_files:
                cmd = cmd + filtered_changed_paths  # type: ignore
            success = self._run_one(cmd, working_dir=check.working_dir)
            if not success:
                self._print_status(check.name, red("failed"))
                self.num_failed_checks += 1
                if check.fix_cmd and self.config.autofix or check.autofix:
                    self.failed_fixable_checks.append(check)

                if self.config.fail_fast or check.fail_fast or fail_fast:
                    n = len(self.config.pre_commit_checks) - (i + 1)
                    if n > 0:
                        s = "" if n == 1 else "s"
                        print()
                        self._print_msg(
                            f"Failing fast: skipping {n} subsequent check{s}."
                        )
                        break
            else:
                self._print_status(check.name, green("passed"))

            if i != len(checks) - 1:
                print()

    def _run_pre_commit_fix(
        self,
        all_changed_paths: List[Path],
        *,
        checks: List[PreCommitCheck],
        unstaged: bool,
    ) -> None:
        fixable_checks = [check for check in checks if check.fix_cmd]
        for i, check in enumerate(fixable_checks):
            filtered_changed_paths = filter_paths(all_changed_paths, check.filters)
            if check.skip or not filtered_changed_paths:
                self._print_status(check.name, yellow("skipped"))
                print()
                continue

            self._print_status(check.name, "fixing")
            cmd = check.fix_cmd
            if check.pass_files:
                cmd = cmd + filtered_changed_paths  # type: ignore
            success = self._run_one(cmd, working_dir=check.working_dir)
            if not success:
                # TODO: test for fix failed
                self._print_status(check.name, red("fix failed"))
            else:
                self._print_status(check.name, "finished")
                if not unstaged:
                    proc = subprocess.run(["git", "add"] + filtered_changed_paths, capture_output=True)  # type: ignore
                    if proc.returncode != 0:
                        self._print_status(
                            check.name,
                            yellow("staging fixed files with 'git add' failed"),
                        )

            if i != len(fixable_checks) - 1:
                print()

    def run_commit_msg(self, commit_msg_file: Path) -> None:
        if len(self.config.commit_msg_checks) == 0:
            return

        print()
        print()
        self._print_block_status("checking commit message")

        for i, check in enumerate(self.config.commit_msg_checks):
            name = get_check_name(check)

            self._print_status(name, "running")
            success = self._run_one(check.cmd + [commit_msg_file])
            if not success:
                self._print_status(name, red("failed"))
                self.num_failed_checks += 1
            else:
                self._print_status(name, green("passed"))

            if i != len(self.config.commit_msg_checks) - 1:
                print()

        failed = self._failed()
        if failed:
            print()
            print()
            self._print_msg("commit message (also at .git/COMMIT_EDITMSG)")
            print(commit_msg_file.read_text(), end="")
            self._print_msg("end commit message", flush=True)

        self._summary("Commit")
        if not failed:
            # put some blank lines in between end of iprecommit output and start of 'git commit' output.
            print()
            print()

    def run_pre_push(self, remote: str) -> None:
        current_branch = githelper.get_current_branch()
        last_commit_pushed = githelper.get_last_commit_pushed(remote, current_branch)
        commits = githelper.get_commits(since=last_commit_pushed)

        for i, check in enumerate(self.config.pre_push_checks):
            name = get_check_name(check)

            self._print_status(name, "running")
            success = self._run_one(check.cmd + commits)
            if not success:
                self._print_status(name, red("failed"))
                self.num_failed_checks += 1
            else:
                self._print_status(name, green("passed"))

            if i != len(self.config.pre_push_checks) - 1:
                print()

        self._summary("Push")
        print()
        print()

    def _run_one(self, cmd, *, working_dir=None) -> bool:
        # stderr of check commands is really part of normal output, so pipe it to stdout
        # also makes it easier to assert on intermingled stdout/stderr in tests
        do_it = lambda: subprocess.run(cmd, stderr=subprocess.STDOUT)

        if working_dir is not None:
            with contextlib.chdir(working_dir):
                proc = do_it()
        else:
            proc = do_it()

        return proc.returncode == 0

    def _get_checks_to_run(
        self, only_list: List[str], skip_list: List[str]
    ) -> List[PreCommitCheck]:
        if len(only_list) > 0 and len(skip_list) > 0:
            raise IPrecommitError("either --skip or --only can be passed, but not both")

        checks = self.config.pre_commit_checks[:]

        def raise_unknown_check_error(name: str) -> NoReturn:
            options = "\n".join(sorted(f"  - {check.name}" for check in checks))
            raise IPrecommitError(
                f"{name!r} is not the name of a known checks. Options:\n\n{options}\n"
            )

        if len(skip_list) > 0:
            skip_set = set(name.lower() for name in skip_list)
            for name in skip_set:
                found = False
                for check in checks:
                    if name == check.name.lower():
                        check.skip = True
                        found = True

                if not found:
                    raise_unknown_check_error(name)

            return checks
        elif len(only_list) > 0:
            only_set = {name.lower(): name for name in only_list}
            for check in checks:
                check_name = check.name.lower()
                if check_name in only_set:
                    only_set.pop(check_name)
                else:
                    check.skip = True

            if len(only_set) > 0:
                _, any_example = only_set.popitem()
                raise_unknown_check_error(any_example)

            return checks
        else:
            return checks

    def _failed(self) -> bool:
        return self.num_failed_checks > 0

    def _summary(self, action: str) -> None:
        if self._failed():
            s = f"{self.num_failed_checks} failed"
            print()
            print()
            print(f"{red(s)}. {action} aborted.")
            sys.stdout.flush()
            sys.exit(1)

    def _print_block_status(self, line: str) -> None:
        stars = "*" * len(line)
        self._print_msg(stars)
        self._print_msg(line)
        self._print_msg(stars)
        print()
        print()
        sys.stdout.flush()

    def _print_status(self, name: str, status: str) -> None:
        self._print_msg(f"{name}: {status}", flush=True)

    def _print_msg(self, line: str, *, flush: bool = False) -> None:
        print(f"{cyan('[iprecommit]')} {line}")
        if flush:
            sys.stdout.flush()


def _parse_skip_envvar():
    val = os.environ.get("IPRECOMMIT_SKIP")
    if val is None:
        return []
    else:
        return [s.strip() for s in val.split(",")]


def get_check_name(check: Union[PreCommitCheck, PrePushCheck, CommitMsgCheck]) -> str:
    if check.name is not None:
        return check.name
    else:
        return " ".join(map(shlex.quote, check.cmd))


def filter_paths(paths: List[Path], filters: List[str]) -> List[Path]:
    if not filters:
        return paths

    if filters[0].startswith("!"):
        filters = ["*"] + filters

    compiled_filters = [compile_filter(f) for f in filters]

    base_filter = compiled_filters[0]
    compiled_filters = compiled_filters[1:]

    pairs: Iterable[Tuple[Path, bool]] = (base_filter((path, False)) for path in paths)
    for f in compiled_filters:
        pairs = map(f, pairs)

    return [item for item, include_me in pairs if include_me]


def compile_filter(pat: str):
    if pat.startswith("!"):
        return lambda pair: (
            (pair[0], False) if fnmatch.fnmatch(pair[0], pat[1:]) else pair
        )
    else:
        return lambda pair: ((pair[0], True) if fnmatch.fnmatch(pair[0], pat) else pair)
