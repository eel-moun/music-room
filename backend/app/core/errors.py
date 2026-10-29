from fastapi import HTTPException


def api_error(status: int, code: str, message: str, **extra: object) -> HTTPException:
    """Error with a stable machine-readable `code` the app can switch on."""
    return HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


def not_found(what: str) -> HTTPException:
    # Also used when the resource exists but the caller may not see it,
    # so private resources don't leak their existence.
    return api_error(404, "not_found", f"{what} not found")


def forbidden(code: str, message: str) -> HTTPException:
    return api_error(403, code, message)
