from __future__ import annotations # for RetryConfig in from_cfg
from dataclasses import dataclass, field
from typing import Tuple, TYPE_CHECKING

import aiohttp # for  aiohttp.ClientError in RetryPolicy
import asyncio # for asyncio.TimeoutError in RetryPolicy


if TYPE_CHECKING:
    from config.config_models import RetryConfig 

@dataclass
class RetryPolicy:
    retries: int = 3
    delay: float = 1.0
    backoff_factor: float = 2.0
    exceptions: Tuple[type, ...] = (aiohttp.ClientError, asyncio.TimeoutError)
    status_codes: Tuple[int, ...] = (408, 429, 500, 502, 503, 504)
    max_delay: float = 30.0

    @classmethod
    def from_cfg(cls, retry_cfg: "RetryConfig") -> "RetryPolicy":
        """Create *RetryPolicy* from pydantic ``RetryConfig`` instance."""
        return cls(
            retries=retry_cfg.count,
            delay=retry_cfg.delay,
            backoff_factor=retry_cfg.backoff_factor,
        )

@dataclass
class HttpSettings:
    timeout: int = 30
    connect_timeout: int = 10
    delay_between_requests: float = 0.0
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    use_proxy: bool = False
    max_connections: int = 100
    limit_per_host: int = 10
    keepalive_timeout: int = 15 