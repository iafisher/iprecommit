from precommitlib import checks


def init(precommit):
    # Generic checks
    precommit.check(checks.NoStagedAndUnstagedChanges())
    precommit.check(checks.NoWhitespaceInFilePath())
    precommit.check(checks.DoNotSubmit())

    # Python checks
    precommit.check(checks.PythonFormat(), exclude="test_repo")
    precommit.check(
        checks.PythonStyle(args=["--max-line-length=88"]), exclude="test_repo"
    )

    # Test suite
    precommit.check(checks.RepoCommand("./test"), slow=True)
