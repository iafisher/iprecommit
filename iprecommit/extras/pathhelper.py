import sys
from pathlib import Path
from typing import Generator, List, Tuple

from iprecommit import githelper
from iprecommit.common import IPrecommitError


def iterate_over_paths(paths: List[Path]) -> Generator[Tuple[str, Path], None, None]:
    for pathstr in paths:
        path = Path(pathstr)
        try:
            text = path.read_text()
        except IsADirectoryError:
            print(f"skipping directory: {pathstr}", file=sys.stderr)
            continue
        except UnicodeDecodeError:
            print(f"skipping non-UTF-8 file: {pathstr}", file=sys.stderr)
            continue

        yield text, path


# Generates `(text, display_title)` pairs, where `display_title` is a string that can be printed
# out to the user.
def iterate_over_paths_and_commits(
    paths: List[Path], commits: List[str]
) -> Generator[Tuple[str, str], None, None]:
    both = bool(paths) and bool(commits)

    for text, path in iterate_over_paths(paths):
        display_title = f"path: {path}" if both else str(path)
        yield text, display_title

    for commit in commits:
        if commit == ".git/COMMIT_EDITMSG":
            raise IPrecommitError(
                "You passed '.git/COMMIT_EDITMSG' as a commit. "
                + "Did you mean --paths instead of --commits in your 'commit_msg' check?"
            )

        message = githelper.get_commit_message(commit)
        display_title = f"commit: {commit}" if both else commit
        yield message, display_title
