A simple tool to manage pre-commit hooks for git.

I wrote it to standardize and automate the repetitive steps of setting up and maintaining pre-commit hooks for git. It's tailored to my personal workflow, but if you'd like to try it yourself you can install it like this (**warning**: the tool is under active development and I may make breaking changes to the API without prior notice):

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


## User guide
The `precommit.py` file that `precommit` generates will look something like this:

```python
from precommitlib import checks


def init(precommit):
    # Generic checks
    precommit.check(checks.NoStagedAndUnstagedChanges())
    precommit.check(checks.NoWhitespaceInFilePath())

    # Language-specific checks
    precommit.check(checks.PythonFormat())
    precommit.check(checks.PythonStyle())
    precommit.check(checks.JavaScriptStyle())
```

The file must define a function called `init` that accepts a `Precommit` object as a parameter. You are not intended to run `precommit.py` directly. You should always invoke it using the `precommit` command.

The default `precommit.py` file has checks for a number of languages. If a language isn't used in your project, the check for that language will never be run, so there's no overhead to keeping the check in the file.

`Precommit.check` registers a pre-commit check. Checks are run in the order they are registered. The built-in checks know what kind of files they should be invoked on, so `checks.PythonFormat` will only run on Python files, and likewise for `checks.PythonStyle`. If you want to limit a check to a certain set of files, `Precommit.check` accepts a `pattern` parameter which should be a regular expression string that matches the files that the check should run on:

```python
# Only disallow whitespace in file path in the src/ directory.
precommit.check(checks.NoWhiteSpaceInFilePath(), pattern=r"^src/.+$")
# You can also exclude patterns.
precommit.check(checks.PythonFormat(), exclude=r"setup\.py")
```

Since `precommit.py` is a Python file, you can disable checks simply by commenting them out.

Some pre-commit checks require other programs to be installed on the computer, e.g. `PythonFormat` requires the `black` code formatter. `precommit init` will **not** install these automatically. You have to install them yourself.

### Writing your own checks
`precommitlib` comes with some useful checks out of the box, but sometimes you need to write your own checks. Doing so is straightforward.

If you just need to run a shell command and check that its exit status is zero, you can use the built-in `checks.Command` check:

```python
precommit.check(checks.Command("./test"))
```

If you need the command to run once per file, use `per_file=True`:

```python
precommit.check(checks.Command("check_file", per_file=True))
```

If `per_file` is True, then for each staged file `Command` will invoke the command with the arguments you passed in its constructor plus the file path at the end. For example, if `a.txt` and `b.txt` were the staged files, then the `Command` check registered above would run `check_file a.txt` and `check_file b.txt`.

If you only want to run the command once, but you still want it to receive the list of file paths as command-line arguments, then use `per_file=False` and `pass_files=True`:

```python
precommit.check(checks.Command("check_file", per_file=False, pass_files=True))
```

#### Writing custom checks in Python
If you need to write custom logic in Python, you should define a class that inherits from either `precommitlib.FileCheck` or `precommitlib.RepoCheck`. The former is for checks that run on every staged file (or every staged file matching a certain pattern) and the latter is for checks that run once for the whole repository.

Here's an example of a custom file check:

```python
from precommitlib import FileCheck, Problem

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
from precommitlib import FileCheck, Problem

class UnitTestsUpdated(FileCheck):
    """Checks that a Python file's unit tests are updated."""

    def check(self, repository):
        for path in repository.filtered:
            if path.endswith(".py") and not path.endswith("_test.py"):
                testpath = os.path.splitext(path)[0] + "_test.py"
                if not testpath in repository.staged_files:
                    return Problem(message="did not update unit tests")
```

In most cases, the only attribute of `repository` you should look at is `filtered`, which lists the file paths that the check should apply to, respecting any custom patterns or exclusions that the user set. The `repository` object also has `staged_files` and `unstaged_files` attributes which list all the staged and unstaged files in the git repository.

Repository checks are less common than file checks. One use case is for commands that can optionally accept a list of file paths instead of just one, like the `flake8` linter for Python. You could write a file check that invokes `flake8` once for each file path, but it's more efficient to invoke it once for the entire repository.

Checks can have class-level `pattern` and `exclude` attributes with the same function as the parameters of `Precommit.check`. This is useful, for example, for checks that should only run on files with certain extensions, like language-specific linters and formatters. Arguments to `Precommit.check` take precedence over the value of class-level attributes.


## API reference
TODO
