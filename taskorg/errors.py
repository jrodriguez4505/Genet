class InvariantError(Exception):
    """Raised when a coded authority or stop rule is violated."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")
