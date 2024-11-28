A dead-simple tool to manage pre-commit hooks for Git.

`iprecommit` runs shell commands and fails the hook if they fail. You can filter commands on glob patterns (e.g., `*.py` for Python-only checks) and define fix commands (e.g., for auto-formatters).

```python
from iprecommit import Checks

checks = Checks()
checks.pre_commit("black", "--check", filters=["*.py"], fix=["black"])
checks.pre_commit("mypy", filters=["*.py"])
checks.pre_commit("./run_tests", pass_files=False)
checks.run()
```

That's it. No YAML configuration or dependency management.

## Getting started
Install it with `pip` or [`pipx`](https://github.com/pypa/pipx):

```shell
pip install iprecommit
```

Then, initialize a pre-commit check in your git repository:

```shell
cd path/to/some/git/repo
iprecommit install
```

`iprecommit install` will create a file called `precommit.py` and install it as a Git pre-commit check.

Now, whenever you run `git commit`, the checks in `precommit.py` will be run automatically. You can also run the pre-commit checks manually:

```shell
iprecommit run
```

Some pre-commit issues can be fixed automatically:

```shell
iprecommit fix
```

By default, `iprecommit run` and `iprecommit fix` operate only on staged changes. To only consider unstaged changes as well, pass the `--unstaged` flag.


## User guide
The `precommit.py` file that `iprecommit install` generates will look something like this:

```python
from iprecommit import Checks

checks = Checks()
checks.pre_commit("iprecommit-no-forbidden-strings", "--paths", name="iprecommit-no-forbidden-strings")
checks.pre_commit("iprecommit-newline-at-eof")

# commit-msg checks
checks.commit_msg("iprecommit-commit-msg-format", "--max-line-length", "72")

checks.run()
```

`iprecommit` comes with some built-in checks, e.g. `iprecommit-no-forbidden-strings`, but you use any existing shell command. Suppose you want to use `black` to enforce Python formatting:

```python
checks.pre_commit("black", "--check", filters=["*.py"], fix=["black"])
```

`iprecommit` currently supports three kinds of hooks:

- `checks.pre_commit()`, run before every commit. The command is passed the list of files that changed (added or modified), unless `pass_files=False`.
- `checks.commit_msg()`, run on the commit message before a commit is finalized. The command is passed a filename holding the commit message.
- `checks.pre_push()`, run on a set of commit hashes before they are pushed to a remote. The command is passed the list of commit hashes.
