A dead-simple tool to manage pre-commit hooks for Git.

`iprecommit` runs shell commands and fails the hook if they fail. You can filter commands on glob patterns (e.g., `*.py` for Python-only checks) and define fix commands (e.g., for auto-formatters).

```toml
[[pre_commit]]
cmd = ["black", "--check"]
filters = ["*.py"]
fix_cmd = ["black"]

[[pre_commit]]
cmd = ["./run_tests"]
pass_files = false
```

That's it.

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

`iprecommit install` will create a file called `precommit.toml` to configure your pre-commit checks.

Now, whenever you run `git commit`, the checks in `precommit.toml` will be run automatically. You can also run the pre-commit checks manually:

```shell
iprecommit run
```

Some pre-commit issues can be fixed automatically:

```shell
iprecommit fix
```

By default, `iprecommit run` and `iprecommit fix` operate only on staged changes. To only consider unstaged changes as well, pass the `--unstaged` flag. To run on every file in the repository (committed, unstaged, and staged), pass the `--all` flag.


## User guide
### Pre-commit checks
```toml
[[pre_commit]]
name = "PythonFormat"
cmd = ["black", "--check"]
filters = ["*.py"]
fix_cmd = ["black"]
```

- `name` is optional.
- Changed files are passed to the command unless `pass_files = false`.
- `filters` is applied to the set of staged files. If the result is empty, the check is not run. Filters may be literal paths (`example.py`), glob patterns (`*.py`), or exclude patterns (`!example.py`, `!*.py`).
- If `fix_cmd` is present, then `iprecommit fix` will *unconditionally* run the command. `filters` still applies as usual.
- Commands run in the root of the Git repository by default. If you need the command to run elsewhere, set `working_dir`.

### Commit message checks
```toml
# commit-msg checks
[[commit_msg]]
name = "CommitMessageFormat"
cmd = ["iprecommit-commit-msg-format", "--max-line-length", "72"]
```

- `name` and `cmd` are the only supported keys for `commit_msg` checks.
- `cmd` is passed the name of a single file which holds the message's contents.

### Pre-push checks
```toml
# pre-push checks (run on commit messages)
[[pre_push]]
name = "NoForbiddenStrings"
cmd = ["iprecommit-no-forbidden-strings", "--commits"]
```

- `name` and `cmd` are the only supported keys for `pre_push` checks.
- `cmd` is passed a list of Git revisions to be pushed to the remote repository.

## Custom commands
These commands are designed to be used with `iprecommit`, but they can also be used independently.

- `iprecommit-commit-msg-format` checks the format of the commit message.
- `iprecommit-newline-at-eof` checks that each file ends with a newline.
- `iprecommit-no-forbidden-strings` checks for forbidden strings.
- `iprecommit-typos` checks for common typos.

## Customization
- If you want to create your own template for `precommit.toml` to be used by `iprecommit install`, then set the environment variable `IPRECOMMIT_TOML_TEMPLATE` to the path to the file.
