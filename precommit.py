from iafisher_precommit import Precommit, checks


def main():
    precommit = Precommit()

    # Generic checks
    precommit.register(checks.NoStagedAndUnstagedChanges())
    precommit.register(checks.NoWhitespaceInFilePath())

    # Python checks
    precommit.register(checks.PythonFormat())
    precommit.register(checks.PythonStyle(args=["--max-line-length=88"]))

    # Test suite
    precommit.register(checks.RepoCommand("./test"))

    return precommit
