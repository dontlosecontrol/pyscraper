import asyncio
import logging
import time
from typing import Dict, Any, Callable, Awaitable, TypeVar

import aiohttp

from infrastructure.proxy_manager import ProxyManager
from .http_models import RetryPolicy


T = TypeVar('T')

class Middleware:
    """Composable middleware: accepts the *next* handler and returns awaited result."""

    async def __call__(
        self,
        handler: Callable[[str, str, Dict[str, Any]], Awaitable[T]],
        method: str,
        url: str,
        **kwargs,
    ) -> T:
        return await handler(method, url, **kwargs)


# todo: add logging helpers
class LoggingMiddleware(Middleware):
    """Base middleware providing *logger* attribute and helper log methods."""

    def __init__(self, name: str):
        logger_name = f"{__name__}.{name}"
        self.logger = logging.getLogger(logger_name)



class ProxyMiddleware(LoggingMiddleware):
    """Adds proxy settings to each request when enabled."""

    def __init__(self, proxy_manager: ProxyManager, use_proxy_default: bool):
        super().__init__("ProxyMW")
        self.proxy_manager = proxy_manager
        self.use_proxy_default = use_proxy_default

    async def __call__(
        self, 
        handler: Callable[[str, str, Dict[str, Any]], Awaitable[T]], 
        method: str, 
        url: str, 
        **kwargs
    ) -> T:
        # prepare proxy if enabled
        use_proxy = kwargs.pop("use_proxy", self.use_proxy_default)
        proxy_address_for_logging = "N/A"
        proxy_data_obtained = None # Flag to check if proxy_data was set

        if use_proxy:
            proxy_data = self.proxy_manager.prepare_proxy()
            proxy_data_obtained = proxy_data # Store proxy_data to check later
            if proxy_data:
                proxy_url = (
                    f"http://{proxy_data['username']}:{proxy_data['password']}@"
                    f"{proxy_data['host']}:{proxy_data['port']}"
                )
                kwargs["proxy"] = proxy_url
                # Auth already included in URL; ensure aiohttp does not add another
                kwargs["proxy_auth"] = None
                proxy_address_for_logging = f"{proxy_data['host']}:{proxy_data['port']}"
                self.logger.debug("Using proxy %s for URL %s", proxy_address_for_logging, url)

        try:
            return await handler(method, url, **kwargs)
        except Exception as exc:
            # Log error only if proxy was intended and proxy_data was actually obtained (not None)
            if use_proxy and self.proxy_manager and proxy_data_obtained:
                self.logger.warning("Error with proxy %s for URL %s: %s", proxy_address_for_logging, url, exc)
                self.proxy_manager.report_error(f"error on {proxy_address_for_logging}")
            raise


class RetryMiddleware(LoggingMiddleware):
    """Implements retry with exponential backoff as outer-layer middleware."""

    def __init__(self, policy: 'RetryPolicy') -> None:
        super().__init__("RetryMW")
        self.policy = policy

    async def __call__(
        self, 
        handler: Callable[[str, str, Dict[str, Any]], Awaitable[T]], 
        method: str, 
        url: str, 
        **kwargs
    ) -> T:
        attempt = 0
        last_exception = None
        
        while attempt <= self.policy.retries:
            try:
                response = await handler(method, url, **kwargs)
                return response
            except Exception as exc:
                last_exception = exc
                attempt += 1
                
                should_retry = False
                
                if isinstance(exc, aiohttp.ClientResponseError) and exc.status in self.policy.status_codes:
                    should_retry = True
                elif any(isinstance(exc, ex_type) for ex_type in self.policy.exceptions):
                    should_retry = True
                
                if not should_retry or attempt > self.policy.retries:
                    raise
                
                wait = min(
                    self.policy.delay * (self.policy.backoff_factor ** (attempt - 1)),
                    self.policy.max_delay
                )
                
                self.logger.warning(
                    "Attempt %s/%s failed for %s: %s (retry in %.2fs)",
                    attempt,
                    self.policy.retries,
                    url,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)
        
        assert last_exception is not None
        raise last_exception



class MetricsMiddleware(LoggingMiddleware):
    """Records request/response metrics."""
    
    def __init__(self):
        super().__init__("MetricsMW")
        self.metrics: Dict[str, Dict[str, Any]] = {} # Ensure metrics is typed
    
    async def __call__(
        self, 
        handler: Callable[[str, str, Dict[str, Any]], Awaitable[T]], 
        method: str, 
        url: str, 
        **kwargs
    ) -> T:
        start_time = time.monotonic() # Use monotonic time for duration
        # Improve domain parsing
        try:
            parsed_url = aiohttp.helpers.URL(url)
            domain = parsed_url.host or "unknown_host"
        except ValueError:
            domain = "invalid_url_host"

        try:
            result = await handler(method, url, **kwargs)
            elapsed = time.monotonic() - start_time
            self._update_domain_metrics(domain, True, elapsed)
            return result
        except Exception as exc:
            elapsed = time.monotonic() - start_time
            self._update_domain_metrics(domain, False, elapsed, exc)
            raise

    def _update_domain_metrics(self, domain: str, success: bool, duration: float, exc: Exception | None = None) -> None:
        """Helper to update metrics for a given domain."""
        if domain not in self.metrics:
            self.metrics[domain] = {
                'count': 0,
                'success': 0,
                'failure': 0,
                'total_time': 0.0,
                'errors': {} # To count specific error types
            }
        
        self.metrics[domain]['count'] += 1
        self.metrics[domain]['total_time'] += duration
        if success:
            self.metrics[domain]['success'] += 1
        else:
            self.metrics[domain]['failure'] += 1
            if exc:
                error_type = type(exc).__name__
                self.metrics[domain]['errors'][error_type] = self.metrics[domain]['errors'].get(error_type, 0) + 1
                
    def get_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Returns the collected metrics."""
        return self.metrics.copy() 