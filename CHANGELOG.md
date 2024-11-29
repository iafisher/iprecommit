# Changelog
All notable changes to `iprecommit` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) with regard to the command-line interface, the format of the `precommit.py` file, and the APIs documented in the README.

**NOTE:** As allowed by Semantic Versioning, backwards compatibility is not guaranteed until version 1.0 is released.

Numbers in parentheses after entries refer to issues in the [GitHub issue tracker](https://github.com/iafisher/iprecommit/issues).

## [0.5.1] - 2024-11-28
- The `IPRECOMMIT_TOML_TEMPLATE` environment variable can be used to customize the `precommit.toml` template.
- `iprecommit fix` will stage changes to files after a fix command modifies them.
- `iprecommit-*` commands now ignore files they cannot parse as UTF-8.

## [0.5.0] - 2024-11-28
- Config format changed from Python (`precommit.py`) to TOML (`precommit.toml`).

## [0.4.0] - 2024-11-28
- Main interface in `precommit.py` is now called `Checks` and has a different API than `Pre`.
- Pure Python checks are no longer supported. All checks must be external shell commands.
- The `iprecommit` package now includes a set of extra commands: `iprecommit-commit-msg-format`, `iprecommit-newline-at-eof`, and `iprecommit-no-forbidden-strings`

## [0.3.1] - 2024-09-30
More API updates.

## [0.3.0] - 2024-09-23
API redesigned, again.

## [0.2.2] - 2024-08-15
- `PythonBlack()` check is added.
- `NO_COLOR` environment variable is respected.

## [0.2.1] - 2024-08-15
- `Precommit.check` and `Precommit.command` take `pattern` and `exclude` parameters to control what files the checks run on.
- The `iprecommit init` command is introduced, to initialize a new pre-commit script from scratch.
- `iprecommit run` and `iprecommit fix` now default to operating on both staged and unstaged changes. The `--unstaged` flag is removed. For the old behavior, pass `--staged`.
- User is warned about misconfigured environment variables.
- README is updated to reflect the new API.

## [0.2] - 2024-08-15
Completely redesigned CLI and Python API.

## [0.1.1] - 2022-07-10
First official release
