from pathlib import Path

from iprecommit.v2 import Changes, NoDoNotSubmitChecker, PrecommitInternal, Reporter


class StubReporter(Reporter):
    failed: bool

    def __init__(self) -> None:
        self.failed = False

    def fail(self, message: str) -> None:
        self.failed = True

    def log(self, message: str) -> None:
        pass

    def verbose(self, message: str) -> None:
        pass


class ReporterFactory:
    def __init__(self):
        self.reporters = []

    def __call__(self):
        reporter = StubReporter()
        self.reporters.append(reporter)
        return reporter


def test_precommit():
    factory = ReporterFactory()
    changes = Changes(
        added_paths=[],
        modified_paths=[Path("tests/examples/includes_do_not_submit.txt")],
        deleted_paths=[],
    )
    pre = PrecommitInternal(changes, reporter_factory=factory)
    pre.check(NoDoNotSubmitChecker())

    assert len(factory.reporters) == 1
    reporter = factory.reporters[0]
    assert reporter.failed
