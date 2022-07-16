# Changelog
All notable changes to iprecommit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) with regard to the command-line interface, the format of the `precommit.py` file, and the APIs documented in the README.

**NOTE:** As allowed by Semantic Versioning, backwards compatibility is not guaranteed until version 1.0 is released.

Numbers in parentheses after entries refer to issues in the [GitHub issue tracker](https://github.com/iafisher/iprecommit/issues).

## Unreleased
### Changed
- The error message for when a `precommit.py` file cannot be found now identifies the directory where `iprecommit` looked for it.

### Fixed
- A misleading error message is no longer printed for import errors of `precommit.py` files. Instead, the Python backtrace is printed.

## [0.1.1] - 2022-07-10
First official release
