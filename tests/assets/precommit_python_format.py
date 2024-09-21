from iprecommit import Precommit, checks

pre = Precommit()
pre.check(checks.PythonFormat())
