class MicroBootstrapBaseError(Exception):
    """Base for all exceptions."""


class ConfigMergeError(MicroBootstrapBaseError):
    """Raises when it's impssible to merge configs due to type mismatch."""
