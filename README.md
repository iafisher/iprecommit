A simple tool to manage pre-commit hooks for git.

I wrote it to standardize and automate the repetitive steps of setting up and maintaining pre-commit hooks for git. It's tailored to my personal workflow, but if you'd like to try it yourself you can install it like this (**warning**: the tool is under active development and I may make breaking changes to the API without prior notice):

```shell
pip3 install git+https://github.com/iafisher/precommit.git
```

Then, you can initialize a pre-commit check in a git repository like this:

```shell
cd path/to/some/git/repo
precommit init
```

`precommit init` will create a file called `precommit.py` in the root of your git repository. `precommit.py` defines your pre-commit hook. It's human-editable and self-explanatory. `precommit init` will automatically install the hook so that it runs whenever you do `git commit`. If you want to run it manually, just run `precommit` with no arguments.

Many pre-commit issues can be fixed automatically. To do so, run

```shell
precommit fix
```

[pre-commit](https://pre-commit.com/) seems to be the most widely-used tool for pre-commit hook management. It's a mature and robust tool that can do many things that my tool can't. The main advantages of my tool are:

- It clearly distinguishes between checking for errors and fixing them.

- It's simple to configure. You just edit a self-explanatory Python file, rather than a YAML file whose schema you have to look up. Defining your pre-commit checks in Python is easy.

- After you install it, you just need to run one command (`precommit init`) to get a working, sensible pre-commit check.

- It's a standalone tool with no dependencies besides Python and git.


## User guide
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

The file must define a function called `init` that accepts a `Checklist` object as a parameter. You are not intended to run `precommit.py` directly. You should always invoke it using the `precommit` command.

The default `precommit.py` file has checks for a number of languages. If a language isn't used in your project, the check for that language will never be run, so there's no overhead to keeping the check in the file.

`Checklist.check` registers a pre-commit check. Checks are run in the order they are registered. The built-in checks know what kind of files they should be invoked on, so `checks.PythonFormat` will only run on Python files, and likewise for `checks.PythonLint`. If you want to limit a check to a certain set of files, the check functions accept a `exclude` parameter which should be a regular expression string that matches the files that the check should not run on:

```python
precommit.check(checks.NoWhiteSpaceInFilePath(exclude=r"^data"))
```

Since `precommit.py` is a Python file, you can disable checks simply by commenting them out.

Some pre-commit checks require other programs to be installed on the computer, e.g. `PythonFormat` requires the `black` code formatter. `precommit init` will **not** install these automatically. You have to install them yourself.

### Writing your own checks
`precommitlib` comes with some useful checks out of the box, but sometimes you need to write your own checks. Doing so is straightforward.

If you just need to run a shell command and check that its exit status is zero, you can use the built-in `checks.Command` check:

```python
precommit.check(checks.Command("UnitTests", ["./test"]))
```

If you need to pass the names of the files to the command, use `pass_files=True`:

```python
precommit.check(checks.Command("FileCheck", ["check_file"], pass_files=True))
```

You can restrict the files that the command runs on with `pattern`:

```python
precommit.check(checks.Command("FileCheck", ["check_file"], pass_files=True, pattern=r".*\.py$"))
```

This will invoke the command `check_file` once, passing every Python file with staged changes as command-line arguments.

If your command only accepts one file at a time, use `separately`:

```python
precommit.check(checks.Command("FileCheck", ["check_file"], pass_files=True, separately=True, pattern=r".*\.py$"))
```

This will invoke the command `check_file` for every Python file with staged changes.


## API reference
TODO


## Missing features
You can see features that I've considered but ultimately rejected by looking at [the GitHub issues marked 'wontfix'](https://github.com/iafisher/precommit/issues?q=is%3Aissue+label%3Awontfix). Some notable ones include:

- Support for file paths not in UTF-8
- Support for pre-commit files named something other than `precommit.py`
- Caching results of pre-commit checks
