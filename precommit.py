from iprecommit import Pre, checks

pre = Pre()
pre.commit.check(checks.NewlineAtEndOfFile())
pre.commit.check(checks.PythonFormat())
pre.commit.sh(".venv/bin/mypy", "iprecommit", base_pattern="*.py")
pre.commit.sh(".venv/bin/flake8", "iprecommit", base_pattern="*.py")
pre.commit.sh(".venv/bin/pytest", "--tb=short", base_pattern="*.py")

pre.push.check(checks.NoDoNotSubmit())

pre.main()
