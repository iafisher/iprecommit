from iprecommit import Pre, checks

pre = Pre()
pre.push.check(checks.NoDoNotPush())
pre.main()
