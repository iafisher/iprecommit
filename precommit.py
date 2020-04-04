from iafisher_precommit import checks, Precommit


def main(args):
    precommit = Precommit()
    precommit.set_args(args)

    # Generic checks
    precommit.register(checks.NoStagedAndUnstagedChanges())
    precommit.register(checks.NoWhitespaceInFilePath())

    # Python checks
    precommit.register(checks.PythonFormat())
    precommit.register(checks.PythonStyle(args=["--max-line-length=88"]))

    precommit.run()
