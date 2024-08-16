#!/usr/bin/env python3
from iprecommit import Precommit, checks

pre = Precommit()
pre.check(checks.NoDoNotSubmit())
pre.check(checks.NewlineAtEndOfFile())
pre.command(["black", "--check"], pass_files=True, pattern=["*.py"])
