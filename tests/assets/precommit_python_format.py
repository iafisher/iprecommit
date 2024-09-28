from iprecommit import Pre, checks

pre = Pre()
pre.commit.check(checks.PythonFormat())
pre.main()
