from iprecommit import Precommit, checks


pre = Precommit()
pre.sh("black", "--check", pass_files="True", base_pattern="*.py")
