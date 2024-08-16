A simple tool to manage pre-commit hooks for Git.

Install it with `pip`:

```shell
pip install iprecommit
```

Then, initialize a pre-commit check in your git repository:

```shell
cd path/to/some/git/repo
iprecommit init
```

`iprecommit init` will create a file called `hooks/precommit.py`, and install it as a Git pre-commit check. You can customize the location with the `--hook` flag.

Now, whenever you run `git commit`, the checks in `precommit.py` will be run automatically. You can also run the pre-commit checks manually:

```shell
iprecommit run
```

Some pre-commit issues can be fixed automatically. To do so, run

```shell
iprecommit fix
```

By default, `iprecommit run` and `iprecommit fix` operate on both staged and unstaged changes. To only consider staged changes, pass the `--staged` flag. (Note that the real pre-commit check only looks at staged changes.)


## User guide
### Precommit file format
The `precommit.py` file that `precommit` generates will look something like this:

```python
from iprecommit import Precommit, checks

pre = Precommit()
pre.check(checks.NoDoNotSubmit())
pre.check(checks.NewlineAtEndOfFile())
pre.command(["black", "--check"], pass_files=True, pattern=["*.py"])
```

`iprecommit` comes with some built-in checks, such as `NoDoNotSubmit()` and `NewlineAtEndOfFile()`. You can also use `pre.command(...)` to define your own checks based on shell commands. These checks will pass as long as the shell command returns an exit code of 0.

By default, `pre.command(...)` will just invoke the command. If you need to pass file names to the command, specify `pass_files=True`. Only changed files will be passed. You can constrain the files to be passed using `pattern`, which takes a list of glob patterns interpreted the same way as `fnmatch.fnmatch`, and `exclude`.

### Writing your own checks
`iprecommit` comes with some useful checks out of the box, but sometimes you need to write your own checks. Doing so is straightforward.

Checks are Python classes that inherit from `BaseCheck`. They must provide a single function, `check`, which takes a parameter of type `Changes` and returns a list of `Message` objects.

- The `Changes` object has three fields: `added_files`, `modified_files`, and `deleted_files`, each of which is a list of `Path` objects.
- The `Message` object has two fields: `message` and `path`. Currently, `path` is not printed, so if the exact file path is important, you should include it in the human-readable `message` field so that the user knows what file it is talking about.

`check` should return one `Message` for each failure it identifies. If it returns an empty list, the pre-commit check is considered to have passed.
