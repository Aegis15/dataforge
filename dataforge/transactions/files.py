"""Filesystem primitives shared by DataForge transaction apply/revert paths."""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path


class SourceLockError(RuntimeError):
    """Raised when a source file lock cannot be acquired."""


def fsync_parent_directory(path: Path) -> None:
    """Best-effort fsync of a path's parent directory after atomic replacement."""
    parent = path.resolve().parent
    try:
        fd = os.open(parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Write bytes to ``path`` through an atomic same-directory replacement."""
    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temp_path = resolved.with_name(f".{resolved.name}.{secrets.token_hex(8)}.tmp")
    try:
        with temp_path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, resolved)
        fsync_parent_directory(resolved)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def lock_path_for(source_path: Path) -> Path:
    """Return the filesystem lock path for a source file."""
    digest = hashlib.sha256(str(source_path.resolve()).encode("utf-8")).hexdigest()[:24]
    return source_path.resolve().parent / ".dataforge" / "locks" / f"{digest}.lock"


@contextmanager
def source_path_lock(
    source_path: Path,
    *,
    timeout_seconds: float = 5.0,
    stale_after_seconds: float = 300.0,
) -> Iterator[None]:
    """Acquire an exclusive lock for a source path using an atomic lock file."""
    lock_path = lock_path_for(source_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                payload = f"{os.getpid()} {datetime.now(UTC).isoformat()}\n".encode()
                os.write(fd, payload)
            finally:
                os.close(fd)
            break
        except FileExistsError as exc:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except OSError:
                age = 0.0
            if age > stale_after_seconds:
                try:
                    lock_path.unlink()
                    continue
                except OSError:
                    pass
            if time.monotonic() >= deadline:
                raise SourceLockError(
                    f"Timed out waiting for DataForge source lock: {source_path.resolve()}"
                ) from exc
            time.sleep(0.05)

    try:
        yield
    finally:
        with suppress(FileNotFoundError):
            lock_path.unlink()
