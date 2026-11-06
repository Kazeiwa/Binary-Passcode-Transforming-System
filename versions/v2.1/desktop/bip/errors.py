class PasscodeError(ValueError):
    """A user-facing error; never contains private keys or whole plaintexts."""

class AuthenticationError(PasscodeError):
    pass

class Cancelled(PasscodeError):
    pass

class InsufficientBlocksError(PasscodeError):
    """Authenticated current-format blocks were found, but fewer than required."""

def checkpoint(cancel=None):
    if cancel is not None and cancel.is_set():
        raise Cancelled("操作已取消。")
