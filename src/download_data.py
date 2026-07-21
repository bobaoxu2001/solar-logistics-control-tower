"""Acquire the SCMS Delivery History Dataset and verify its integrity.

The official USAID portal (data.usaid.gov) went offline in 2025, so the file
is fetched from public mirrors. Every download is verified against a pinned
SHA-256 (originally cross-validated between two independent mirrors), so a
tampered or truncated mirror copy is rejected.

Usage:
    python src/download_data.py
"""

from __future__ import annotations

import hashlib
import shutil
import ssl
import sys
import tempfile
import urllib.request
from pathlib import Path

from common import PROJECT_ROOT, ensure_dirs, get_logger, load_config

log = get_logger("download_data")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(url, timeout=120, context=ctx) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)


def main() -> int:
    cfg = load_config()["source_dataset"]
    ensure_dirs()
    target = PROJECT_ROOT / cfg["local_path"]
    expected = cfg["sha256"]

    if target.exists() and sha256_of(target) == expected:
        log.info("Dataset already present and checksum-verified: %s", target)
        return 0

    for url in cfg["mirrors"]:
        log.info("Trying mirror: %s", url)
        tmp = Path(tempfile.mkstemp(suffix=".csv")[1])
        try:
            download(url, tmp)
            digest = sha256_of(tmp)
            if digest == expected:
                shutil.move(tmp, target)
                log.info("Downloaded and verified (sha256=%s…): %s", digest[:12], target)
                return 0
            log.warning("Checksum mismatch from %s (got %s…)", url, digest[:12])
        except Exception as exc:  # noqa: BLE001 — try the next mirror
            log.warning("Mirror failed: %s", exc)
        finally:
            tmp.unlink(missing_ok=True)

    log.error(
        "No mirror produced a file matching sha256=%s. "
        "Place a verified copy manually at %s.", expected, target
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
