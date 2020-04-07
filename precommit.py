from precommitlib import checks


def init(precommit):
    # Generic checks
    precommit.register(checks.NoStagedAndUnstagedChanges())
    precommit.register(checks.NoWhitespaceInFilePath())

    # Python checks
    precommit.register(checks.PythonFormat(), exclude="test_repo")
    precommit.register(
        checks.PythonStyle(args=["--max-line-length=88"]), exclude="test_repo"
    )

    # Test suite
    precommit.register(checks.RepoCommand("./test"), slow=True)
