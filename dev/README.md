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

## Filtering logic
- A check class can define a `base_pattern`, e.g. `*.py` for `PythonFormat`.
- Users can define a list of `Include` and `Exclude` patterns. Later patterns override earlier ones.
  - e.g., if `patterns` is `[Include("*.py"), Exclude("dist/*.py"), Include("dist/main.py")]`, then
    `a.py` is included, `dist/a.py` is excluded, and `dist/main.py` is included.

## Non-UTF-8 filenames
```python
f = open(b"\xc0\xaf.test", "w")
f.write("test\n")
f.close()
```

- On macOS, the above code raises `OSError`.
- On Linux, it works.
- You can't construct a `Path` object with a bytestring, but you can do `bytes.decode("utf8", "surrogateescape")` and this works on Linux -- at least as long as `sys.getfilesystemencodeerrors()` is also set to `surrogateescape`.
- There's a property `os.path.supports_unicode_filenames` which is true for macOS and false for Linux.
