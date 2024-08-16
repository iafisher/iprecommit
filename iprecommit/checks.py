import subprocess
from typing import List, Tuple

from .lib import BaseCheck, BaseCommand, Changes, Message


class NewlineAtEndOfFile(BaseCheck):
    def check(self, changes: Changes) -> List[Message]:
        failures = []
        for path in changes.added_files + changes.modified_files:
            text = path.read_text()
            if not text.endswith("\n"):
                failures.append(
                    Message(
                        message=f"{path} is missing newline at end of file", path=path
                    )
                )

        return failures

    def fix(self, changes: Changes) -> List[Message]:
        messages = self.check(changes)
        for message in messages:
            with open(message.path, "a") as f:
                f.write("\n")

        return messages


class NoDoNotSubmit(BaseCheck):
    def check(self, changes: Changes) -> List[Message]:
        failures = []
        for path in changes.added_files + changes.modified_files:
            with open(path, "r") as f:
                for lineno, line in enumerate(f, start=1):
                    if "DO NOT " + "SUBMIT" in line:
                        failures.append(
                            Message(
                                message="'DO NOT "
                                + f"SUBMIT' found on line {lineno} of {path}",
                                path=path,
                            )
                        )

        return failures


class PythonBlack(BaseCommand):
    def __init__(self) -> None:
        super().__init__(["black", "--check"], pass_files=True)

    def fix(self, changes: Changes) -> List[Message]:
        subprocess.run(["black"] + changes.as_list())
        return [Message("", p) for p in changes.as_list()]

    def get_filters(self) -> Tuple[List[str], List[str]]:
        return ["*.py"], []
