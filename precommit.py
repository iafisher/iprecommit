from iprecommit import Checks

checks = Checks()
checks.pre_commit("iprecommit-no-forbidden-strings", "--paths", name="NoDoNotCommit")
checks.pre_commit("iprecommit-newline-at-eof", name="NewlineAtEndOfFile")
checks.pre_commit(
    "black", "--check", filters=["*.py", "!iprecommit/toml/**/*.py"], fix=["black"], name="PythonFormat"
)
# TODO: should consider deleted files
checks.pre_commit(
    ".venv/bin/mypy",
    "iprecommit",
    pass_files=False,
    filters=["*.py"],
    name="PythonTypes",
)
checks.pre_commit(
    ".venv/bin/flake8",
    "iprecommit",
    pass_files=False,
    filters=["*.py", "!iprecommit/toml/**/*.py"],
    name="PythonLint",
)
# TODO: should consider deleted files
checks.pre_commit(
    ".venv/bin/pytest",
    "--tb=short",
    pass_files=False,
    filters=["*.py"],
    name="ProjectTests",
)

checks.pre_push("iprecommit-do-not-commit", "--commits")

checks.run()
