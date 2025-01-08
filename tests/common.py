import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

owndir = Path(__file__).absolute().parent


class Base(unittest.TestCase):
    def setUp(self):
        os.chdir(self.tmpdir)
        for path in os.listdir():
            if path != ".venv":
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)

    @classmethod
    def setUpClass(cls):
        cls.tmpdir_obj = tempfile.TemporaryDirectory()
        cls.tmpdir = cls.tmpdir_obj.name
        print(f"test: created temporary dir: {cls.tmpdir}")

        os.chdir(cls.tmpdir)

        run_shell(["python3", "-m", "venv", ".venv"])
        print("test: created virtualenv")

        run_shell([".venv/bin/pip", "install", str(owndir.parent)])
        # modify PATH because the precommit.toml template uses the unqualified names of iprecommit commands
        os.environ["PATH"] += os.pathsep + cls.tmpdir + "/.venv/bin"
        print("test: installed iprecommit and iprecommit-extra libraries")

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir_obj.cleanup()

    def _create_repo(
        self, precommit_text=None, install_hook=True, path=None, clean=False
    ):
        os.chdir(self.tmpdir)

        run_shell(["git", "init"])
        print("test: initialized git repo")

        if precommit_text is not None:
            Path("precommit.toml").write_text(precommit_text)

        Path(".gitignore").write_text(".venv\n")

        if install_hook:
            os.environ.pop("IPRECOMMIT_TOML_TEMPLATE", None)
            run_shell(
                [".venv/bin/iprecommit", "install"]
                + (["--path", path] if path is not None else [])
            )
            print("test: installed pre-commit hook")

        if clean:
            run_shell(["git", "add", "."], check=True)
            run_shell(["git", "commit", "-m", "init commit"], check=True)


def run_shell(args, check=True, capture_stdout=False, capture_stderr=False):
    print(f"test: running {args}")
    return subprocess.run(
        args,
        check=check,
        stdout=subprocess.PIPE if capture_stdout else None,
        stderr=subprocess.PIPE if capture_stderr else None,
        text=capture_stdout or capture_stderr,
    )
