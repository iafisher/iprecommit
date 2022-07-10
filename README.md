A simple tool to manage pre-commit hooks for git.

Install it with pip:

```shell
pip3 install git+https://github.com/iafisher/precommit.git
```

Then, initialize a pre-commit check in your git repository:

```shell
cd path/to/some/git/repo
precommit init
```

`precommit init` will create a file called `precommit.py` in the root of your git repository that defines your pre-commit checks. It's human-editable and self-explanatory.

Now, whenever you run `git commit`, the checks in `precommit.py` will be run automatically. You can also run the pre-commit checks manually:

```shell
precommit
```

Many pre-commit issues can be fixed automatically. To do so, run

```shell
precommit fix
```

Pass the `--working` flag to `precommit` and `precommit fix` to operate on both staged and unstaged changes.


## User guide
### Precommit file format
The `precommit.py` file that `precommit` generates will look something like this:

```python
from precommitlib import checks


def init(precommit):
    precommit.check(checks.NoStagedAndUnstagedChanges())
    precommit.check(checks.NoWhitespaceInFilePath())
    precommit.check(checks.DoNotSubmit())

    # Check Python format with black.
    precommit.check(checks.PythonFormat())

    # Lint Python code with flake8.
    precommit.check(checks.PythonLint())

    # Check the order of Python imports with isort.
    precommit.check(checks.PythonImportOrder())

    # Check Python static type annotations with mypy.
    precommit.check(checks.PythonTypes())

    # Lint JavaScript code with ESLint.
    precommit.check(checks.JavaScriptLint())
```

`precommit.py` must define a function called `init` that accepts a single parameter, called `precommit` by convention.

`precommit.check` registers a pre-commit check. Checks are run in the order they are registered. The built-in checks know what kind of files they should be invoked on, so, e.g., `checks.PythonFormat` will only run on Python files. If you want to limit a check to a certain set of files, the check functions accept a `exclude` parameter which should be a list of Unix filename patterns:

```python
precommit.check(checks.NoWhiteSpaceInFilePath(exclude=["data/*.csv"]))
```

You can also opt-in files with the `include` parameter. See the [Python `fnmatch` module](https://docs.python.org/3.6/library/fnmatch.html) for details on the pattern syntax for `exclude` and `include`.

Since `precommit.py` is a Python file, you can disable checks by commenting them out.

The default `precommit.py` has checks for a number of languages. There is no overhead for checks for languages that you don't use. They will simply never be run.

Some pre-commit checks require other programs to be installed on the computer, e.g. `PythonFormat` requires the `black` code formatter. `precommit init` will **not** install these automatically. You have to install them yourself.

### Writing your own checks
`precommitlib` comes with some useful checks out of the box, but sometimes you need to write your own checks. Doing so is straightforward.

To run a shell command and check that its exit status is zero, use the built-in `checks.Command` check:

```python
precommit.check(checks.Command("UnitTests", ["./test"]))
```

If the command requires the names of the files to be passed to it, use `pass_files=True`:

```python
precommit.check(checks.Command("FileCheck", ["check_file"], pass_files=True))
```

Restrict the types of files that the command runs on with `include`:

```python
precommit.check(checks.Command("FileCheck", ["check_file"], pass_files=True, include=["*.py"]))
```

This will invoke the command `check_file` once, passing all files ending in `.py` with staged changes as command-line arguments.

If the command only accepts one file at a time, use `separately`:

```python
precommit.check(checks.Command("FileCheck", ["check_file"], pass_files=True, separately=True, include=["*.py"]))
```

This will invoke `check_file` on each Python file with staged changes.

If you want to implement the logic of your check in Python rather than invoke a shell command, then look at the built-in checks in `precommitlib/checks.py` in this repository for guidance. `DoNotSubmit` is a good example of a simple custom check.


## Development
If you're interested in using this tool, I encourage you to fork your own copy and tailor it to your personal workflow and preferences.

The core logic for running checks and applying fixes is in `precommitlib/lib.py`. The built-in checks are defined in `precommitlib/checks.py`, and the pre-commit configuration template is at `precommitlib/precommit.py.template`.

Run the test suite with `./functional_test`, which simulates an actual user session: creating a git repository and virtual environment, installing precommit, and running it as a shell command.


## Missing features
You can see features that I've considered but ultimately rejected by looking at [the issues marked 'wontfix' on GitHub](https://github.com/iafisher/precommit/issues?q=is%3Aissue+label%3Awontfix). Some notable ones include:

- Support for non-UTF-8 file paths
- Support for customizing the name of `precommit.py`
- Caching results of pre-commit checks
