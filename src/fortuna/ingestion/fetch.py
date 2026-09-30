"""Fetch an official source and store it as an immutable raw artifact.

Phase 0 use only: provenance capture + light verification pulls. Full-scale
historical ingestion is a Phase 1 activity and is NOT implemented here.

Some official hosts (e.g. files.floridalottery.com) reject Python's default
TLS ClientHello while accepting curl's. ``fetch_source`` falls back to a curl
subprocess in that case so provenance capture still works.
"""

import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime

import requests

from fortuna.provenance.store import ArtifactStore
from fortuna.schemas.artifacts import RawArtifact
from fortuna.schemas.sources import Source

DEFAULT_TIMEOUT = float(os.environ.get("FORTUNA_HTTP_TIMEOUT", "30"))
DEFAULT_UA = os.environ.get(
    "FORTUNA_USER_AGENT", "project-fortuna/0.1 (research provenance capture)"
)


@dataclass
class Fetched:
    content: bytes
    mime_type: str
    via: str  # "requests" or "curl"


def _get_requests(url: str, timeout: float) -> Fetched:
    resp = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": DEFAULT_UA},
        allow_redirects=True,
    )
    resp.raise_for_status()
    mime = resp.headers.get("Content-Type", "application/octet-stream")
    return Fetched(resp.content, mime, "requests")


def _get_curl(url: str, timeout: float) -> Fetched:
    import tempfile

    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tmp = tf.name
    try:
        proc = subprocess.run(
            [
                "curl", "-sS", "-L", "-f",
                "--max-time", str(int(timeout)),
                "-A", DEFAULT_UA,
                "-w", "%{content_type}",
                "-o", tmp,
                url,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"curl failed ({proc.returncode}): {proc.stderr.strip()}")
        mime = proc.stdout.strip() or "application/octet-stream"
        content = open(tmp, "rb").read()
        return Fetched(content, mime, "curl")
    finally:
        os.unlink(tmp)


def fetch_bytes(url: str, timeout: float = DEFAULT_TIMEOUT) -> Fetched:
    """Fetch bytes from ``url``, preferring requests with a curl TLS fallback."""
    try:
        return _get_requests(url, timeout)
    except requests.exceptions.SSLError:
        return _get_curl(url, timeout)


def fetch_post_bytes(
    url: str, json_body: dict, timeout: float = DEFAULT_TIMEOUT
) -> Fetched:
    """POST a JSON body and return response bytes (requests; curl fallback)."""
    os.environ.pop("SSLKEYLOGFILE", None)
    try:
        resp = requests.post(
            url,
            json=json_body,
            timeout=timeout,
            headers={"User-Agent": DEFAULT_UA},
        )
        resp.raise_for_status()
        mime = resp.headers.get("Content-Type", "application/octet-stream")
        return Fetched(resp.content, mime, "requests")
    except requests.exceptions.SSLError:
        import tempfile

        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".json", mode="w"
        ) as bf:
            import json as _json

            _json.dump(json_body, bf)
            body_path = bf.name
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tmp = tf.name
        try:
            proc = subprocess.run(
                [
                    "curl", "-sS", "-L", "-f",
                    "--max-time", str(int(timeout)),
                    "-A", DEFAULT_UA,
                    "-H", "Content-Type: application/json",
                    "-d", "@" + body_path,
                    "-w", "%{content_type}",
                    "-o", tmp,
                    url,
                ],
                capture_output=True, text=True, check=False,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"curl POST failed ({proc.returncode}): {proc.stderr.strip()}"
                )
            mime = proc.stdout.strip() or "application/octet-stream"
            return Fetched(open(tmp, "rb").read(), mime, "curl")
        finally:
            os.unlink(tmp)
            os.unlink(body_path)


def fetch_source(
    source: Source,
    store: ArtifactStore,
    timeout: float = DEFAULT_TIMEOUT,
) -> RawArtifact:
    """GET ``source.url`` and store the bytes immutably.

    Returns the created RawArtifact (a new artifact row is always recorded;
    identical content reuses the existing immutable file).
    """
    # A stray SSLKEYLOGFILE pointing at an unwritable path breaks urllib3's
    # SSL context creation; it is a debugging var, never required here.
    os.environ.pop("SSLKEYLOGFILE", None)

    got = fetch_bytes(source.url, timeout)
    filename_hint = source.url.rsplit("/", 1)[-1].split("?")[0] or None
    return store.store(
        source_id=source.source_id,
        content=got.content,
        mime_type=got.mime_type,
        retrieved_at=datetime.now(UTC),
        filename_hint=filename_hint,
    )
