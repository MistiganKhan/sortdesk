"""
In-memory sliding-window rate limiter for authentication endpoints.
Protects against brute-force attacks and credential stuffing without external dependencies.
"""
import time
from collections import defaultdict, deque
from threading import Lock


class SlidingWindowRateLimiter:
    def __init__(self, default_max_attempts: int = 5, default_window_seconds: int = 900):
        self.default_max_attempts = default_max_attempts
        self.default_window_seconds = default_window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _cleanup_stale(self, key: str, now: float, window_seconds: int) -> None:
        queue = self._failures[key]
        threshold = now - window_seconds
        while queue and queue[0] <= threshold:
            queue.popleft()
        if not queue:
            del self._failures[key]

    def is_allowed(
        self,
        key: str,
        max_attempts: int | None = None,
        window_seconds: int | None = None,
    ) -> tuple[bool, int]:
        """
        Checks if the given key (e.g. IP or email) is within rate limits.
        Returns:
            (is_allowed: bool, retry_after_seconds: int)
        """
        max_att = max_attempts or self.default_max_attempts
        win_sec = window_seconds or self.default_window_seconds
        now = time.time()

        with self._lock:
            if key in self._failures:
                self._cleanup_stale(key, now, win_sec)

            if key not in self._failures:
                return True, 0

            attempts = self._failures[key]
            if len(attempts) >= max_att:
                oldest = attempts[0]
                retry_after = max(1, int(oldest + win_sec - now))
                return False, retry_after

            return True, 0

    def record_failure(self, key: str, window_seconds: int | None = None) -> None:
        """Records a failed attempt for the given key."""
        win_sec = window_seconds or self.default_window_seconds
        now = time.time()
        with self._lock:
            self._cleanup_stale(key, now, win_sec)
            self._failures[key].append(now)

    def reset_failures(self, key: str) -> None:
        """Resets failed attempt records for a key after successful authentication."""
        with self._lock:
            if key in self._failures:
                del self._failures[key]

    def get_remaining_attempts(
        self,
        key: str,
        max_attempts: int | None = None,
        window_seconds: int | None = None,
    ) -> int:
        """Returns the number of remaining attempts allowed before lockout."""
        max_att = max_attempts or self.default_max_attempts
        win_sec = window_seconds or self.default_window_seconds
        now = time.time()
        with self._lock:
            if key in self._failures:
                self._cleanup_stale(key, now, win_sec)
            count = len(self._failures.get(key, []))
            return max(0, max_att - count)


# Global rate limiter instance for auth endpoints
auth_rate_limiter = SlidingWindowRateLimiter(
    default_max_attempts=5,
    default_window_seconds=900,  # 15 minutes lockout window
)
