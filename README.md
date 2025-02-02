A dead-simple tool to manage pre-commit hooks for Git.

`iprecommit` runs shell commands and fails the hook if they fail. You can filter commands on glob patterns (e.g., `*.py` for Python-only checks) and define fix commands (e.g., for auto-formatters).

```toml
[[pre_commit]]
name = "PythonFormat"
cmd = ["black", "--check"]
filters = ["*.py"]
fix_cmd = ["black"]

[[pre_commit]]
name = "UnitTests"
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


## FAQs
### Why not pre-commit?
[pre-commit](https://pre-commit.com/) is (as far as I can tell) the most widely-used library for pre-commit hook management.

I used pre-commit for a while. Here's why I created `iprecommit`:

- I hated configuring my pre-commit checks in YAML.
- The colored output is hard to read with a dark theme, and [this won't be fixed](https://github.com/pre-commit/pre-commit/issues/2325).
- I just wanted an intelligent way to run shell commands before `git commit`, not a "multi-language package manager".
- With a custom template at `IPRECOMMIT_TOML_TEMPLATE`, and `autofix` and `fail_fast` set to true, `iprecommit` does what I want and I rarely have to think about it.

Reasons you might prefer pre-commit:

- You like pre-commit's [more extensive configuration options](https://pre-commit.com/#creating-new-hooks).
- You need one of the [Git hooks that pre-commit supports](https://pre-commit.com/#supported-git-hooks) and `iprecommit` doesn't.

### Why not Husky?
[Husky](https://typicode.github.io/husky/) is a pre-commit tool that is popular in the JavaScript ecosystem.

`iprecommit` has a few features that Husky doesn't:

- `iprecommit` can pass only changed files to your checks.
- `iprecommit` checks can auto-fix problems (for instance, reformatting code).
- Husky will stop at the first failing check, while `iprecommit` will run all checks (unless `fail_fast` is set).

### How do I disable a failing check?
Set `IPRECOMMIT_SKIP` to a comma-separated list of checks to skip, e.g.:

```shell
$ IPRECOMMIT_SKIP="Check1,Check2" git commit -m '...'
```

To persistently skip a check, set `skip = true` in the `precommit.toml` file.


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

### Autofix
If the top-level `autofix` option is set to `true` in the TOML file, then when a fixable check fails, `iprecommit run` will automatically invoke `iprecommit fix`, and then re-run `iprecommit run` after. This is useful if you have, e.g., auto-formatting checks that can fix themselves without human intervention.

## Custom commands
These commands are designed to be used with `iprecommit`, but they can also be used independently.

- `iprecommit-commit-msg-format` checks the format of the commit message.
- `iprecommit-newline-at-eof` checks that each file ends with a newline.
- `iprecommit-no-forbidden-strings` checks for forbidden strings.
- `iprecommit-typos` checks for common typos.

## Customization
- If you want to create your own template for `precommit.toml` to be used by `iprecommit install`, then set the environment variable `IPRECOMMIT_TOML_TEMPLATE` to the path to the file.
