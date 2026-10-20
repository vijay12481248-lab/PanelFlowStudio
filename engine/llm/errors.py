class GenerationLimitError(ValueError):
    """A deterministic model budget failure; replaying the same request cannot help."""
    retryable = False

    def __init__(self, reason, generated=None, limit=None):
        self.reason = reason
        super().__init__(f"Model output reached its {reason} limit (generated={generated}, budget={limit}). Use a smaller request.")
