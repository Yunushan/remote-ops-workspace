from __future__ import annotations

from collections import deque


class _ByteChunkQueue:
    """FIFO bytes without repeated front-deletion copies.

    Terminal output can arrive much faster than a QTextEdit can be rebuilt. A
    ``bytearray`` plus ``del buffer[:n]`` moves the whole remaining backlog for
    every render turn and becomes quadratic for large command output. This
    queue keeps immutable chunks and only copies the bounded prefix returned to
    the renderer.
    """

    __slots__ = ("_chunks", "_head_offset", "_size")

    def __init__(self) -> None:
        self._chunks: deque[bytes] = deque()
        self._head_offset = 0
        self._size = 0

    def __bool__(self) -> bool:
        return self._size > 0

    def __len__(self) -> int:
        return self._size

    def append(self, payload: bytes) -> None:
        data = bytes(payload)
        if not data:
            return
        self._chunks.append(data)
        self._size += len(data)

    def clear(self) -> None:
        self._chunks.clear()
        self._head_offset = 0
        self._size = 0

    def take(self, max_bytes: int) -> bytes:
        requested = min(self._size, max(0, int(max_bytes)))
        if requested <= 0:
            return b""
        remaining = requested
        parts: list[bytes] = []
        while remaining:
            chunk = self._chunks[0]
            available = len(chunk) - self._head_offset
            amount = min(available, remaining)
            parts.append(chunk[self._head_offset : self._head_offset + amount])
            self._head_offset += amount
            self._size -= amount
            remaining -= amount
            if self._head_offset == len(chunk):
                self._chunks.popleft()
                self._head_offset = 0
        if len(parts) == 1:
            return parts[0]
        return b"".join(parts)
