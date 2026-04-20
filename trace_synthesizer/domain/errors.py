"""Domain-level errors for CFG and trace handling."""


class TraceSynthesizerError(Exception):
    """Base exception for the package."""


class InvalidCfgError(TraceSynthesizerError):
    """CFG JSON violates structural invariants."""


class UnknownFunctionError(TraceSynthesizerError):
    """Requested function is not present in the program."""


class InvalidTransitionError(TraceSynthesizerError):
    """A BB transition is not allowed by the static CFG."""


class EmptyTraceError(TraceSynthesizerError):
    """Trace input contains no mappable events."""
