import sys
from pathlib import Path
from typing import Generator, List, Tuple

from . import githelper


# Generates `(text, display_title)` pairs, where `display_title` is a string that can be printed
# out to the user.
def iterate_over_paths_and_commits(
    paths: List[Path], commits: List[str]
) -> Generator[Tuple[str, str], None, None]:
    both = bool(paths) and bool(commits)

    for pathstr in paths:
        try:
            text = Path(pathstr).read_text()
        except IsADirectoryError:
            print(f"skipping directory: {pathstr}", file=sys.stderr)
            continue
        except UnicodeDecodeError:
            print(f"skipping non-UTF-8 file: {pathstr}", file=sys.stderr)
            continue

        display_title = f"path: {pathstr}" if both else str(pathstr)
        yield text, display_title

    for commit in commits:
        message = githelper.get_commit_message(commit)
        display_title = f"commit: {commit}" if both else commit
        yield message, display_title
