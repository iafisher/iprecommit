from typing import List

from .lib import BaseCheck, Changes, Failure


class NewlineAtEndOfFile(BaseCheck):
    def check(self, changes: Changes) -> List[Failure]:
        failures = []
        for path in changes.added_files + changes.modified_files:
            text = path.read_text()
            if not text.endswith("\n"):
                failures.append(
                    Failure(message=f"{path} is missing newline at end of file")
                )

        return failures


class NoDoNotSubmit(BaseCheck):
    def check(self, changes: Changes) -> List[Failure]:
        failures = []
        for path in changes.added_files + changes.modified_files:
            text = path.read_text()
            if "DO NOT " + "SUBMIT" in text:
                failures.append(
                    Failure(message=f"'DO NOT " + "SUBMIT' found in {path}")
                )

        return failures
