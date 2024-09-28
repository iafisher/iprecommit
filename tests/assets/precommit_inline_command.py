from iprecommit import Pre


pre = Pre()
pre.commit.sh("black", "--check", pass_files="True", base_pattern="*.py")
pre.main()
