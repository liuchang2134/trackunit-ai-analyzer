"""Per-request selection of demonstration or Trackunit-backed data."""
from contextvars import ContextVar, Token

_mode: ContextVar[str | None] = ContextVar('jilian_data_mode', default=None)


def selected_mode() -> str | None:
    return _mode.get()


def set_mode(value: str | None) -> Token:
    if value not in (None, 'demo', 'live'):
        raise ValueError('Unsupported data mode')
    return _mode.set(value)


def reset_mode(token: Token) -> None:
    _mode.reset(token)
