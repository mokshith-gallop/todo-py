"""Helpers to normalise DATABASE_URL for asyncpg.

The platform may inject a URL like:
    postgresql://user:pass@host:5432/db?sslmode=require

asyncpg does NOT understand the ``sslmode`` query-param (it raises
``TypeError: connect() got an unexpected keyword argument 'sslmode'``).
We must:
  1. Swap the scheme to ``postgresql+asyncpg://``
  2. Strip ``sslmode`` from the query string
  3. Translate the original ``sslmode`` value into an ``ssl`` connect_arg
     that asyncpg *does* accept.
"""

import ssl
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def normalise_url(raw: str) -> str:
    """Return a URL safe for SQLAlchemy + asyncpg (no ``sslmode`` param)."""
    if not raw:
        return raw

    # Ensure asyncpg driver prefix
    if raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+asyncpg://", 1)

    parsed = urlparse(raw)
    qs = parse_qs(parsed.query)

    # Drop sslmode — we handle it via connect_args instead
    qs.pop("sslmode", None)

    clean_query = urlencode(qs, doseq=True)
    cleaned = parsed._replace(query=clean_query)
    return urlunparse(cleaned)


def connect_args_for_url(raw: str) -> dict:
    """Return ``connect_args`` dict (``ssl`` key) derived from the URL.

    - ``sslmode=require|verify-ca|verify-full`` →  SSL context
    - ``sslmode=disable|prefer`` or absent on localhost → no SSL
    - Remote host with no explicit sslmode → SSL (safe default)
    """
    parsed = urlparse(raw)
    qs = parse_qs(parsed.query)
    sslmode = (qs.get("sslmode") or [None])[0]
    host = parsed.hostname or ""

    is_local = host in ("localhost", "127.0.0.1", "")

    need_ssl = False
    if sslmode in ("require", "verify-ca", "verify-full"):
        need_ssl = True
    elif sslmode in ("disable",):
        need_ssl = False
    elif not is_local:
        # Remote host, default to SSL
        need_ssl = True

    if need_ssl:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return {"ssl": ctx}

    return {}
