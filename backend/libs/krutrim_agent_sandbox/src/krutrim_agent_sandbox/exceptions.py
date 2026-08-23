class SandboxError(Exception):
    """Base class for sandbox failures."""


class SandboxStartError(SandboxError):
    """The sandbox container could not be started."""
