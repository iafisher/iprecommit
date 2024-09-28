from iprecommit import Precommit, checks


class NoTypos(checks.Base):
    typos = {"programing": "programming"}

    def check(self, changes):
        for path in changes.added_paths + changes.modified_paths:
            text = path.read_text()
            for typo in self.typos:
                if typo in text:
                    return False

        return True

    def fix(self, changes):
        for path in changes.added_paths + changes.modified_paths:
            text = path.read_text()
            for typo, fixed in self.typos.items():
                text = text.replace(typo, fixed)

            path.write_text(text)


pre = Precommit()
pre.check(NoTypos())
pre.main()
