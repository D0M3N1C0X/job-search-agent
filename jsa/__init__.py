"""job-search-agent — a deterministic job-search pipeline with an LLM on top."""

import sys

__version__ = "1.0.0"

MINIMUM_PYTHON = (3, 10)

if sys.version_info < MINIMUM_PYTHON:  # pragma: no cover - checked before anything imports
    have = ".".join(str(n) for n in sys.version_info[:3])
    need = ".".join(str(n) for n in MINIMUM_PYTHON)
    sys.exit(
        f"job-search-agent needs Python {need} or newer, and this is Python {have}\n"
        f"  ({sys.executable})\n\n"
        "macOS ships an older Python at /usr/bin/python3. Install a current one with\n"
        "  brew install python\n"
        "or from https://www.python.org/downloads/ , then run the command again."
    )
