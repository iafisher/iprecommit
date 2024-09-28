from iprecommit import Pre, checks

pre = Pre()
pre.push.check(checks.NoDoNotSubmit())
pre.main()
