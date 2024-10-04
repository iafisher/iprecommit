from iprecommit import Pre, checks

pre = Pre()
pre.commit_msg.check(checks.CommitMessageFormat(require_capitalized=True))
pre.main()
