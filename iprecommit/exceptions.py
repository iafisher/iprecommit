class IPrecommitError(Exception):
    pass


# Not a subclass of `IPrecommitError` so we don't accidentally catch it.
class IPrecommitUserError(Exception):
    pass


# Not a subclass of `IPrecommitError` so we don't accidentally catch it.
class IPrecommitImpossibleError(Exception):
    def __init__(self) -> None:
        super().__init__(
            "This error should never happen. If you see it, please contact an iprecommit developer."
        )
