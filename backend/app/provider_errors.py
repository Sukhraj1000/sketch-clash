"""Local control failures are never evidence of a Google provider failure."""


class LocalProviderControlError(Exception):
    """An application admission, budget, cancellation or storage issue."""
