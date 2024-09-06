*This README is for developers working on `iprecommit` itself. Users of `iprecommit` should consult the README in the project root instead.*

## Publish a new version
1. Bump `version` in `pyproject.toml`.
2. Add a new section to `CHANGELOG.md`.
3. Make a commit with message `Version X.Y.Z`.
4. Push to GitHub.
5. Create a release on GitHub titled `Version X.Y.Z`, creating a tag called `vX.Y.Z`.
6. Run `git pull --tags`.
7. Run `poetry build`.
8. Run `poetry publish`.

## Running tests
Unit tests:

```shell
$ pytest
```

Functional test:

```shell
$ ./functional_test
```
