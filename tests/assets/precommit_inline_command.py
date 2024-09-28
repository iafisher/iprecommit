from iprecommit import Precommit


pre = Precommit()
pre.sh("black", "--check", pass_files="True", base_pattern="*.py")
pre.main()
