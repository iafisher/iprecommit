import contextlib
import fnmatch
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Tuple, Union

from . import githelper, tomlconfig
from .common import cyan, green, red, yellow
from .tomlconfig import CommitMsgCheck, PreCommitCheck, PrePushCheck


class Checks:
    num_failed_checks: int
    failed_fixable_checks: bool
    config: tomlconfig.Config

    def __init__(self, config: tomlconfig.Config) -> None:
        self.num_failed_checks = 0
        self.failed_fixable_checks = False
        self.config = config

    def run_pre_commit(
        self, *, fix_mode: bool, unstaged: bool, all_files: bool
    ) -> None:
        assert not (unstaged and all_files)

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
        else:
            all_changed_paths = (
                githelper.get_changed_paths(include_unstaged=unstaged)
                + githelper.get_untracked_files()
            )

        if fix_mode:
            self._run_pre_commit_fix(all_changed_paths, unstaged=unstaged)
        else:
            if self.config.autofix:
                self._run_pre_commit_check(all_changed_paths)

                if self.num_failed_checks > 0 and self.failed_fixable_checks:
                    print()
                    print()
                    self._print_block_status("attempting autofix")
                    self._run_pre_commit_fix(all_changed_paths, unstaged=unstaged)

                    self.num_failed_checks = 0
                    print()
                    print()
                    self._print_block_status("retrying after autofix")
                    self._run_pre_commit_check(all_changed_paths)
            else:
                self._run_pre_commit_check(all_changed_paths)

        self._summary("Commit")

    def _run_pre_commit_check(self, all_changed_paths: List[Path]) -> None:
        for i, check in enumerate(self.config.pre_commit_checks):
            name = get_check_name(check)

            filtered_changed_paths = filter_paths(all_changed_paths, check.filters)
            if not filtered_changed_paths:
                self._print_status(name, yellow("skipped"))
                continue

            self._print_status(name, "running")
            cmd = check.cmd
            # TODO: test where pass_files=False
            if check.pass_files:
                cmd = cmd + filtered_changed_paths  # type: ignore
            success = self._run_one(cmd, working_dir=check.working_dir)
            if not success:
                self._print_status(name, red("failed"))
                self.num_failed_checks += 1
                if check.fix_cmd:
                    self.failed_fixable_checks = True

                if self.config.fail_fast or check.fail_fast:
                    n = len(self.config.pre_commit_checks) - (i + 1)
                    if n > 0:
                        s = "" if n == 1 else "s"
                        print()
                        self._print_msg(
                            f"Failing fast: skipping {n} subsequent check{s}."
                        )
                        break
            else:
                self._print_status(name, green("passed"))

            if i != len(self.config.pre_commit_checks) - 1:
                print()

    def _run_pre_commit_fix(
        self, all_changed_paths: List[Path], *, unstaged: bool
    ) -> None:
        fixable_checks = [
            check for check in self.config.pre_commit_checks if check.fix_cmd
        ]
        for i, check in enumerate(fixable_checks):
            name = get_check_name(check)

            filtered_changed_paths = filter_paths(all_changed_paths, check.filters)
            if not filtered_changed_paths:
                self._print_status(name, yellow("skipped"))
                continue

            self._print_status(name, "fixing")
            cmd = check.fix_cmd
            if check.pass_files:
                cmd = cmd + filtered_changed_paths  # type: ignore
            success = self._run_one(cmd, working_dir=check.working_dir)
            if not success:
                # TODO: test for fix failed
                self._print_status(name, red("fix failed"))
            else:
                self._print_status(name, "finished")
                if not unstaged:
                    proc = subprocess.run(["git", "add"] + filtered_changed_paths, capture_output=True)  # type: ignore
                    if proc.returncode != 0:
                        self._print_status(
                            name,
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


def get_check_name(check: Union[PreCommitCheck, PrePushCheck, CommitMsgCheck]) -> str:
    if check.name is not None:
        return check.name
    else:
        return " ".join(map(shlex.quote, check.cmd))


def filter_paths(paths: List[Path], filters: List[str]) -> List[Path]:
    if not filters:
        return paths

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
