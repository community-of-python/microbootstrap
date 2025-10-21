class MicroBootstrapBaseError(Exception):
    """Base for all exceptions."""


class ConfigMergeError(MicroBootstrapBaseError):
    """Raises when it's impossible to merge configs due to type mismatch."""


class MissingInstrumentError(MicroBootstrapBaseError):
    """Raises when attempting to configure instrument, that is not supported yet."""


class BootstrapperConfigurationError(MicroBootstrapBaseError):
    """Raises when there is something wrong with bootstrapper configuration."""
