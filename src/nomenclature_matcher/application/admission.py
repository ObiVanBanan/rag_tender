"""In-process admission control for costly synchronous LLM-backed batches.

The budget accounts for attempted item-level matching operations, not USD or
actual provider tokens. Multi-process and global monetary caps must be enforced
upstream or by providers. Rejected batches NEVER invoke the matcher.
"""
from __future__ import annotations

import math
from collections import deque
from contextlib import contextmanager
from threading import BoundedSemaphore, Lock
from time import monotonic
from typing import Callable, Iterator


class AdmissionRejected(Exception):
    def __init__(self, reason: str, retry_after_seconds: int = 1) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retry_after_seconds = retry_after_seconds


class RequestAdmission:
    """Thread-safe single-process admission with fixed rolling 60-min window."""

    WINDOW_SECONDS = 3600

    def __init__(
        self,
        *,
        max_inflight_batches: int = 1,
        max_items_per_hour: int = 500,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_inflight_batches <= 0 or max_items_per_hour <= 0:
            raise ValueError("Admission limits must be positive")
        self.max_items_per_hour = max_items_per_hour
        self._clock = clock
        self._semaphore = BoundedSemaphore(max_inflight_batches)
        self._lock = Lock()
        self._attempts: deque[tuple[float, int]] = deque()
        self._reserved_items = 0

    def _expire(self, now: float) -> None:
        while self._attempts and self._attempts[0][0] <= now - self.WINDOW_SECONDS:
            _, units = self._attempts.popleft()
            self._reserved_items -= units

    @contextmanager
    def reserve(self, items: int) -> Iterator[None]:
        """Reject up front before any paid provider calls.

        A reservation is *not* refunded on provider failure: such attempts may
        already have incurred charges and must count against the budget.
        """
        if items <= 0:
            raise ValueError("items must be positive")
        if items > self.max_items_per_hour:
            raise AdmissionRejected("BATCH_EXCEEDS_HOURLY_LIMIT", 3600)
        if not self._semaphore.acquire(blocking=False):
            raise AdmissionRejected("MATCHER_BUSY", 1)
        try:
            with self._lock:
                now = self._clock()
                self._expire(now)
                excess = self._reserved_items + items - self.max_items_per_hour
                if excess > 0:
                    for timestamp, units in self._attempts:
                        excess -= units
                        if excess <= 0:
                            retry_after = max(
                                1, math.ceil(timestamp + self.WINDOW_SECONDS - now)
                            )
                            break
                    else:
                        retry_after = self.WINDOW_SECONDS
                    raise AdmissionRejected("HOURLY_ITEM_LIMIT_REACHED", retry_after)
                self._attempts.append((now, items))
                self._reserved_items += items
            yield
        finally:
            self._semaphore.release()
