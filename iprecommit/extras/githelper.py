import subprocess


def get_commit_message(rev: str) -> str:
    proc = subprocess.run(
        ["git", "log", "-1", rev, "--format=%B"],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout
