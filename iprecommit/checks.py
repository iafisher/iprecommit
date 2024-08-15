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
            with open(path, "r") as f:
                for lineno, line in enumerate(f, start=1):
                    if "DO NOT " + "SUBMIT" in line:
                        failures.append(
                            Failure(
                                message="'DO NOT "
                                + f"SUBMIT' found on line {lineno} of {path}"
                            )
                        )

        return failures
