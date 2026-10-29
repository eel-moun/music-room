"""Every authorization rule lives here, as pure functions (no database, no I/O).

Routes load the facts (is the caller the owner? invited? a friend?), then ask a
policy. Keeping the rules apart makes them unit-testable and easy to audit.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    allowed: bool
    code: str = ""
    message: str = ""


ALLOW = Decision(True)


def deny(code: str, message: str) -> Decision:
    return Decision(False, code, message)
