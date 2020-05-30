from precommitlib import checks


def init(precommit):
    # Generic checks
    precommit.check(checks.NoStagedAndUnstagedChanges())
    precommit.check(checks.NoWhitespaceInFilePath())
    precommit.check(checks.DoNotSubmit())

    # Language-specific checks
    precommit.check(checks.PythonFormat(exclude=["test_repo/*"]))
    precommit.check(checks.PythonLint(exclude=["test_repo/*"]))
    precommit.check(checks.PythonTypes(exclude=["test_repo/*"]))
    precommit.check(checks.PipFreeze())

    # Test suite
    precommit.check(
        checks.Command(
            "FunctionalTests", ["./functional_test"], exclude=["*.md"], slow=True
        )
    )
