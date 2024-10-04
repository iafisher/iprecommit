from iprecommit import Pre, checks

pre = Pre()
pre.commit.check(checks.NewlineAtEndOfFile())
pre.commit.check(checks.PythonFormat())
# TODO: should consider deleted files
pre.commit.sh(".venv/bin/mypy", "iprecommit", base_pattern="*.py", name="PythonTypes")
pre.commit.sh(".venv/bin/flake8", "iprecommit", base_pattern="*.py", name="PythonLint")
# TODO: should consider deleted files
pre.commit.sh(
    ".venv/bin/pytest", "--tb=short", base_pattern="*.py", name="ProjectTests"
)

pre.push.check(checks.NoDoNotCommit())

pre.main()
