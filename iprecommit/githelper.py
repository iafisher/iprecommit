import os
import subprocess
from pathlib import Path
from typing import List, Optional


def get_commit_message(rev: str) -> str:
    proc = subprocess.run(
        ["git", "log", "-1", rev, "--format=%B"],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def get_current_branch() -> str:
    # TODO: can a git branch name be non-UTF8?
    result = subprocess.run(
        ["git", "branch", "--show-current"], capture_output=True, text=True
    )
    return result.stdout.strip()


def get_last_commit_pushed(remote: str, branch: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", f"{remote}/{branch}"], capture_output=True, text=True
    )
    if result.returncode == 0:
        return result.stdout.strip()
    else:
        # the empty commit allows us to diff from beginning of git history
        # this is the case when no commits have been pushed to the remote
        return get_diff_for_empty_commit()


def get_diff_for_empty_commit() -> str:
    # courtesy of https://stackoverflow.com/questions/40883798
    # TODO: handle error code
    result = subprocess.run(
        ["git", "hash-object", "-t", "tree", "/dev/null"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def any_staged_changes() -> bool:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], capture_output=True
    )
    return len(result.stdout) > 0


def get_changed_paths(
    *, include_unstaged: bool, since: Optional[str] = None
) -> List[Path]:
    added_paths = _filter_paths("A", include_unstaged=include_unstaged, since=since)
    modified_paths = _filter_paths("M", include_unstaged=include_unstaged, since=since)
    renamed_paths = _filter_paths("R", include_unstaged=include_unstaged, since=since)
    return added_paths + modified_paths + renamed_paths


def get_deleted_paths(*, include_unstaged: bool) -> List[Path]:
    return _filter_paths("D", include_unstaged=include_unstaged, since=None)


def get_tracked_files() -> List[Path]:
    proc = subprocess.run(
        ["git", "ls-tree", "-r", "HEAD", "--name-only", "-z"],
        capture_output=True,
        check=True,
    )
    return _decode_path_list(proc.stdout)


def get_untracked_files() -> List[Path]:
    proc = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        capture_output=True,
        check=True,
    )
    return _decode_path_list(proc.stdout)


def get_commits(*, since: str) -> List[str]:
    # TODO: what if pushing to a different branch?
    proc = subprocess.run(
        ["git", "log", f"{since}..HEAD", "--format=%H"],
        capture_output=True,
        check=True,
        text=True,
    )
    return proc.stdout.splitlines()


def _filter_paths(
    filter_string, *, include_unstaged: bool, since: Optional[str] = None
):
    if since is not None:
        ref = since
    elif include_unstaged:
        ref = "HEAD"
    else:
        ref = "--cached"

    result = subprocess.run(
        ["git", "diff", ref, "--name-only", f"--diff-filter={filter_string}", "-z"],
        capture_output=True,
    )
    return _decode_path_list(result.stdout)


def _decode_path_list(stdout: bytes) -> List[Path]:
    return [Path(os.fsdecode(p)) for p in stdout.split(b"\x00") if p]
