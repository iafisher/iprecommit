A simple tool to manage pre-commit hooks for Git.

Install it with `pip`:

```shell
pip install iprecommit
```

Then, initialize a pre-commit check in your git repository:

```shell
cd path/to/some/git/repo
iprecommit template
iprecommit install
```

`iprecommit template` will create a file called `precommit.py`, and `iprecommit install` will install it as a Git pre-commit check.

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
### Precommit file format
The `precommit.py` file that `precommit` generates will look something like this:

```python
from iprecommit import Precommit, checks

pre = Precommit()
pre.check(checks.NoDoNotSubmit())
pre.check(checks.NewlineAtEndOfFile())
pre.sh("black", "--check", pass_files=True, base_pattern="*.py")
```

`iprecommit` comes with some built-in checks, such as `NoDoNotSubmit()` and `NewlineAtEndOfFile()`. You can also use `pre.sh(...)` to define your own checks based on shell commands. These checks will pass as long as the shell command returns an exit code of 0.

You can also define your own checks in Python:

```python
class NoTypos(checks.Base):
    typos = {
        "programing": "programming"
    }

    def check(self, changes):
        for path in changes.added_paths + changes.modified_paths:
            text = path.read_text()
            for typo in self.typos:
                if typo in text:
                    return False
            
        return True
    
    def fix(self, changes):
        for path in changes.added_paths + changes.modified_paths:
            text = path.read_text()
            for typo, fixed in self.typos.items():
                text = text.replace(typo, fixed)

            path.write_text(text)
```
