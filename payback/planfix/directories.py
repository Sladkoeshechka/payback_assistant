"""Cached directory reads for category and direction selection."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Protocol

from payback.planfix.models import PlanfixDirectory, PlanfixDirectoryEntry

_DIRECTORY_TTL_SECONDS = 600.0


class DirectoryClient(Protocol):
    """Minimal Planfix surface needed to load directory entries."""

    async def get_directory(self, directory_id: int) -> PlanfixDirectory: ...

    async def list_directory_entries(
        self, directory_id: int, title_field_id: int
    ) -> list[PlanfixDirectoryEntry]: ...


@dataclass(frozen=True, slots=True)
class _CachedDirectory:
    loaded_at: float
    entries: tuple[PlanfixDirectoryEntry, ...]


class DirectoryCache:
    """Cache Planfix directory entries and keep the last good result on outages."""

    def __init__(
        self,
        client: DirectoryClient,
        *,
        ttl_seconds: float = _DIRECTORY_TTL_SECONDS,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._cached: dict[int, _CachedDirectory] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    async def get(self, directory_id: int) -> tuple[PlanfixDirectoryEntry, ...]:
        cached = self._cached.get(directory_id)
        if cached is not None and self._is_fresh(cached):
            return cached.entries

        lock = self._locks.setdefault(directory_id, asyncio.Lock())
        async with lock:
            cached = self._cached.get(directory_id)
            if cached is not None and self._is_fresh(cached):
                return cached.entries
            try:
                directory = await self._client.get_directory(directory_id)
                entries = tuple(
                    await self._client.list_directory_entries(
                        directory.id, directory.title_field_id
                    )
                )
            except Exception:
                if cached is not None:
                    return cached.entries
                raise
            self._cached[directory_id] = _CachedDirectory(self._clock(), entries)
            return entries

    def invalidate(self, directory_id: int | None = None) -> None:
        """Forget one directory or all of them for the future ``/refresh`` command."""
        if directory_id is None:
            self._cached.clear()
        else:
            self._cached.pop(directory_id, None)

    def _is_fresh(self, cached: _CachedDirectory) -> bool:
        return self._clock() - cached.loaded_at < self._ttl_seconds


__all__ = ["DirectoryCache", "DirectoryClient"]
