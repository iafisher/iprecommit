from iprecommit import Pre, checks

pre = Pre()
pre.commit_msg.check(checks.CommitMessageIsCapitalized())
pre.main()
