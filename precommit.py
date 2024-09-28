from iprecommit import Precommit, checks

pre = Precommit()
pre.check(checks.NoDoNotSubmit())
pre.check(checks.NewlineAtEndOfFile())
pre.check(checks.PythonFormat())
pre.sh(".venv/bin/mypy", "iprecommit", base_pattern="*.py")
pre.sh(".venv/bin/flake8", "iprecommit", base_pattern="*.py")
pre.sh(".venv/bin/pytest", base_pattern="*.py")
pre.main()
