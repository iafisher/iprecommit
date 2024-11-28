*This README is for developers working on `iprecommit` itself. Users of `iprecommit` should consult the README in the project root instead.*

## Publish a new version
1. Bump `version` in `pyproject.toml`.
2. Add a new section to `CHANGELOG.md`.
3. Make a commit with message `version X.Y.Z`.
4. Push to GitHub.
5. Create a release on GitHub titled `Version X.Y.Z`, creating a tag called `vX.Y.Z`.
6. Run `git pull --tags`.
7. Run `poetry build`.
8. Run `poetry publish`.

## Running tests
```shell
$ pytest
```

To debug, it's helpful to place a breakpoint (`import pdb; pdb.set_trace()`) and print `self.tmpdir`. Then, you can `cd` to that directory in the shell and manually inspect the state of the repository with `git`, run `iprecommit`, etc.
