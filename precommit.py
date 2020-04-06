from iafisher_precommit import checks


def init(precommit):
    # Generic checks
    precommit.register(checks.NoStagedAndUnstagedChanges())
    precommit.register(checks.NoWhitespaceInFilePath())

    # Python checks
    precommit.register(checks.PythonFormat())
    precommit.register(checks.PythonStyle(args=["--max-line-length=88"]))

    # Test suite
    precommit.register(checks.RepoCommand("./test"), slow=True)
