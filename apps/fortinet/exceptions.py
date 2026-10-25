class FortinetError(Exception):
    """Sanitized remote failure suitable for a user-facing result."""


class UncertainResult(FortinetError):
    """A mutation might have been applied. Never retry it blindly."""
