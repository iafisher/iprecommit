from iprecommit import Pre, checks

pre = Pre()
pre.push.check(checks.NoDoNotCommit())
pre.main()
