"""Job sources.

Every source is a callable that yields `Job` objects. They are registered here
so `jsa fetch` can run them all without a central config, and so adding a
market means adding one function.
"""

from __future__ import annotations

from typing import Callable, Iterable

from ..models import Job

Fetcher = Callable[..., Iterable[Job]]
REGISTRY: dict[str, Fetcher] = {}


def register(name: str) -> Callable[[Fetcher], Fetcher]:
    def wrap(fn: Fetcher) -> Fetcher:
        REGISTRY[name] = fn
        return fn
    return wrap


from . import ats, linkedin, mailbox  # noqa: E402,F401  (import for side effects)

__all__ = ["REGISTRY", "register", "ats", "linkedin", "mailbox"]
