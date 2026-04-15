from __future__ import annotations

from abc import ABC, abstractmethod


class TokenBlocklistBackend(ABC):
    """Abstract base class for token blocklist storage backends.

    Implementations must provide fast JTI lookups and automatic
    expiration of entries to avoid unbounded memory growth.
    """

    @abstractmethod
    async def block(self, jti: str, expires_at: int) -> None:
        """Add a JTI to the blocklist.

        Args:
            jti: The unique JWT ID (jti claim) to block.
            expires_at: Unix timestamp when the token naturally expires.
                       Used to calculate TTL for automatic cleanup.
        """
        ...

    @abstractmethod
    async def is_blocked(self, jti: str) -> bool:
        """Check if a JTI is in the blocklist.

        Args:
            jti: The JWT ID to check.

        Returns:
            True if the token is blocked, False otherwise.
        """
        ...

    async def cleanup(self) -> int:
        """Remove expired entries from the blocklist.

        Backends that use automatic TTL expiration (e.g. Redis) should
        return 0 since cleanup is handled automatically.

        Returns:
            Number of entries removed.
        """
        return 0
