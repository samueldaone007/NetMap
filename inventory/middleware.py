"""Thread-local access to the authenticated user for change logging."""
from contextvars import ContextVar

_current_user = ContextVar("netmap_current_user", default=None)


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _current_user.set(
            request.user if getattr(request, "user", None) and request.user.is_authenticated else None
        )
        try:
            return self.get_response(request)
        finally:
            _current_user.reset(token)


def get_current_user():
    return _current_user.get()
