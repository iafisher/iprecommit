#!/usr/bin/env python3
from iprecommit import Precommit, checks

pre = Precommit()
pre.check(checks.NoDoNotSubmit())
pre.check(checks.NewlineAtEndOfFile())
pre.check(checks.PythonBlack())
pre.command(["./functional_test"], exclude=["*.md"])
