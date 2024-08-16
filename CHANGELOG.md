# Changelog
All notable changes to iprecommit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) with regard to the command-line interface, the format of the `precommit.py` file, and the APIs documented in the README.

**NOTE:** As allowed by Semantic Versioning, backwards compatibility is not guaranteed until version 1.0 is released.

Numbers in parentheses after entries refer to issues in the [GitHub issue tracker](https://github.com/iafisher/iprecommit/issues).

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
