"""Env-backed settings.

Loads `.env` into os.environ so entry points see the values a developer put
there. Python does not read `.env` files natively, so without this the
collector and seeder read os.environ, find nothing, and silently skip every
source -- which looks exactly like "no API key configured" even when the key is
sitting in `.env`.

Deliberately stdlib-only. `pydantic-settings` is in requirements.txt and is the
right tool for the FastAPI app's typed settings later, but the collector is a
cron-run script whose only other dependencies are stdlib, and a dotenv parser
is twenty lines. Keeping it dependency-free means the collector cannot fail to
start because of an unrelated dependency problem.

Security: values are never logged, printed, or returned. `load_dotenv` returns
the KEYS it set, never the values, so a caller cannot casually log a secret.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV = PROJECT_ROOT / ".env"


def load_dotenv(path: Path | None = None, override: bool = False) -> list[str]:
    """Load KEY=value pairs from `path` into os.environ.

    Returns the list of key NAMES that were set -- never the values.

    A missing file is not an error: deployment may supply real environment
    variables instead, and that path must work identically.

    By default a variable already present in the environment WINS over the
    file. An explicit `export FOO=...` or a CI secret should not be silently
    overridden by a stale local `.env`. Pass override=True to invert that.
    """
    path = path or DEFAULT_ENV
    if not path.is_file():
        return []

    loaded: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue

        value = value.strip()
        # Strip one matching pair of surrounding quotes. Keys pasted from a
        # provider dashboard often arrive quoted, and a literal quote inside
        # the value breaks auth in a way that is annoying to diagnose.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        if not value:
            continue  # an empty assignment means "unset", not "set to ''"
        if key in os.environ and not override:
            continue

        os.environ[key] = value
        loaded.append(key)

    return loaded


def configured(*keys: str) -> dict[str, bool]:
    """Report which of `keys` have a non-empty value. Values are not returned."""
    return {k: bool(os.environ.get(k)) for k in keys}
