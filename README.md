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

By default, `iprecommit run` and `iprecommit fix` operate only on staged changes. To only consider unstaged changes as well, pass the `--unstaged` flag.


## User guide
The `precommit.toml` file that `iprecommit install` generates will look something like this:

```toml
[[pre_commit]]
name = "NoForbiddenStrings"
cmd = ["iprecommit-no-forbidden-strings", "--paths"]

[[pre_commit]]
name = "NewlineAtEndOfFile"
cmd = ["iprecommit-newline-at-eof"]

# [[pre_commit]]
# name = "PythonFormat"
# cmd = ["black", "--check"]
# filters = ["*.py"]
# fix_cmd = ["black"]

# [[pre_commit]]
# name = "ProjectTests"
# cmd = ["./run_tests"]
# pass_files = false

# commit-msg checks
[[commit_msg]]
name = "CommitMessageFormat"
cmd = ["iprecommit-commit-msg-format", "--max-line-length", "72"]

# pre-push checks (run on commit messages)
[[pre_push]]
name = "NoForbiddenStrings"
cmd = ["iprecommit-no-forbidden-strings", "--commits"]
```

`iprecommit` comes with some built-in checks, e.g. `iprecommit-no-forbidden-strings`, but you can use any shell command.

`iprecommit` currently supports three kinds of hooks:

- `[[pre_commit]]`, run before every commit. The command is passed the list of files that changed (added or modified), unless `pass_files = false`.
- `[[commit_msg]]`, run on the commit message before a commit is finalized. The command is passed a filename holding the commit message.
- `[[pre_push]]`, run on a set of commit hashes before they are pushed to a remote. The command is passed the list of commit hashes.

## Custom checks
These checks are designed to be used with `iprecommit`, but they can also be used independently.

- `iprecommit-commit-msg-format` checks the format of the commit message.
- `iprecommit-newline-at-eof` checks that each file ends with a newline.
- `iprecommit-no-forbidden-strings` checks for forbidden strings.
- `iprecommit-typos` checks for common typos.

## Customization
- If you want to create your own template for `precommit.toml` to be used by `iprecommit install`, then set the environment variable `IPRECOMMIT_TOML_TEMPLATE` to the path to the file.
