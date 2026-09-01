class InvariantError(Exception):
    """Raised when a coded authority or stop rule is violated."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")
