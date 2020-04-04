A simple tool to manage pre-commit hooks for git.

I wrote it to standardize and automate the repetitive steps of setting up and maintaining pre-commit hooks for git. It's tailored to my personal workflow, but if you'd like to try it yourself you can install it like this:

```shell
pip3 install git+https://github.com/iafisher/precommit.git
cd path/to/some/git/repo
precommit init
```

`precommit init` will create a file called `precommit.py` in the root of your git repository. `precommit.py` defines your pre-commit hook. It's human-editable and self-explanatory. `precommit init` will automatically install the hook so that it runs whenever you do `git commit`. If you want to run it manually, just run `precommit` with no arguments.

Many pre-commit issues can be fixed automatically. To do so, run

```shell
precommit fix
```

[pre-commit](https://pre-commit.com/) seems to be the most widely-used tool for pre-commit hook management. It's a mature and robust tool that can do many things that my tool can't. The main advantages of my tool are:

- It can automatically fix some pre-commit errors. This is the main reason I wrote it.

- It's simple to configure. You just edit a self-explanatory Python file, rather than a YAML file whose schema you have to look up. Defining your pre-commit checks in Python is easy.

- After you install it, you just need to run one command (`precommit init`) to get a working, sensible pre-commit check.

- It's a standalone tool with no dependencies besides Python and git.


## Writing your own pre-commit checks
The `precommit.py` file that `precommit` generates will look something like this:

```python
from iafisher_precommit import Precommit, checks


def main():
    precommit = Precommit()

    # Generic checks
    precommit.register(checks.NoStagedAndUnstagedChanges())
    precommit.register(checks.NoWhitespaceInFilePath())

    # Python checks
    precommit.register(checks.PythonFormat())
    precommit.register(checks.PythonStyle())

    return precommit
```

The file must define a function called `main` that returns a `Precommit` object. You are not intended to run `precommit.py` directly. You should always invoke it using the `precommit` command.

`Precommit.register` registers a pre-commit check. Checks are run in the order they are registered. The built-in checks know what kind of files they should be invoked on, so `checks.PythonFormat` will only run on Python files, and likewise for `checks.PythonStyle`. If you want to limit a check to a certain set of files, `Precommit.register` accepts a `pattern` parameter which should be a regular expression string that matches the files that the check should run on:

```python
# Only disallow whitespace in file path in the src/ directory.
precommit.register(checks.NoWhiteSpaceInFilePath(), pattern=r"^src/.+$")
```

As you can see, the `iafisher_precommit` library comes with some useful checks out of the box, but sometimes you need to write your own checks. Doing so is straightforward.

If you just need to run a shell command and check that its exit status is zero, you can use the built-in `checks.RepoCommand` class:

```python
precommit.register(checks.RepoCommand(["./test"]))
```

`RepoCommand` will run the exact command you give it once for the whole repository. If you need to run a command for every staged file, use `FileCommand` instead:

```python
precommit.register(checks.FileCommand(["check_file"]))
```

For each staged file, `FileCommand` will invoke the command with the arguments you passed in its constructor plus the file path at the end. For example, if `a.txt` and `b.txt` were the staged files, then the `FileCommand` check registered above would run `check_file a.txt` and `check_file b.txt`.

If you need to write custom logic in Python, you should define a class that inherits from either `iafisher_precommit.FileCheck` or `iafisher_precommit.RepoCheck`. The former is for checks that run on every staged file (or every staged file matching a certain pattern) and the latter is for checks that run once for the whole repository.

Here's an example of a custom file check:

```python
from iafisher_precommit import FileCheck, Problem

class NoBadCharactersInPath(FileCheck):
    """Checks that the file path contains no bad characters."""

    def __init__(self, bad=" ?;()[]"):
        self.bad = bad

    def check(self, path):
        if any(c in path for c in self.bad):
            return Problem(message="bad character in file path")
```

The file check class defines `check` method that takes in a file path. It returns either `None` if there are no problems, or a `Problem` object with an error message. It can also return a list of `Problem` objects.

And here's an example of a custom repository check:

```python
import os
from iafisher_precommit import FileCheck, Problem

class UnitTestsUpdated(FileCheck):
    """Checks that a Python file's unit tests are updated."""

    def check(self, repo_info):
        for path in repo_info.staged_files:
            if path.endswith(".py") and not path.endswith("_test.py"):
                testpath = os.path.splitext(path)[0] + "_test.py"
                if not testpath in repo_info.staged_files:
                    return Problem(message="did not update unit tests")
```

Usually, you'll define these custom checks in `precommit.py`.
