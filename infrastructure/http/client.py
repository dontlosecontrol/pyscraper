from __future__ import annotations

import asyncio
import logging
from typing import Optional, Dict, Any, List, Callable, Tuple, Union, Awaitable, TypeVar, cast

import aiohttp
from aiohttp import ClientTimeout, TCPConnector

from config.config_manager import ConfigManager
from config.config_models import RetryConfig
from infrastructure.proxy_manager import ProxyManager

from .middlewares import Middleware, LoggingMiddleware, ProxyMiddleware, RetryMiddleware, MetricsMiddleware
from .http_models import HttpSettings, RetryPolicy

T = TypeVar('T')



class HttpClient:
    """Асинхронный HTTP-клиент со встроенным retry и поддержкой middleware."""

    def __init__(
        self,
        config_manager: ConfigManager,
        settings: Optional[HttpSettings] = None,
        middlewares: Optional[List[Middleware]] = None,
    ) -> None:
        self.config_manager = config_manager
        self.settings = settings or self._settings_from_global_config()
        self.logger = logging.getLogger(__name__)
        self.session: Optional[aiohttp.ClientSession] = None
        self.last_request_time: float = 0.0
        
        self.middlewares: List[Middleware] = []
        
        self.metrics_middleware = MetricsMiddleware()
        self.middlewares.append(self.metrics_middleware)

        self.middlewares.append(RetryMiddleware(self.settings.retry))

        if self.settings.use_proxy or self.config_manager.config.use_proxy:
            proxy_mw = ProxyMiddleware(
                ProxyManager(
                    proxy_file=self.config_manager.config.proxy.file,
                    max_requests_per_proxy=self.config_manager.config.max_requests_per_proxy or 10,
                ),
                use_proxy_default=self.settings.use_proxy or self.config_manager.config.use_proxy,
            )
            self.middlewares.append(proxy_mw)

        if middlewares: 
            self.middlewares.extend(middlewares)

    # ---------------- public API ----------------

    async def __aenter__(self):
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    def get_metrics(self) -> Dict[str, Dict[str, Any]]:
        return self.metrics_middleware.get_metrics()

    async def get(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        use_proxy: Optional[bool] = None,
        timeout: Optional[int] = None,
    ) -> Optional[str]:
        return await self._request(
            "GET",
            url,
            params=params,
            headers=headers,
            use_proxy=use_proxy,
            timeout=timeout,
            response_type="text",
        )
        return cast(Optional[str], result)

    async def post(
        self,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        response_type: str = "text",
        use_proxy: Optional[bool] = None,
        timeout: Optional[int] = None,
    ) -> Optional[Union[str, Dict[str, Any], bytes]]:
        return await self._request(
            "POST",
            url,
            headers=headers,
            json=json,
            data=data,
            use_proxy=use_proxy,
            timeout=timeout,
            response_type=response_type,
        )

    def _settings_from_global_config(self) -> HttpSettings:  # noqa: D401 – simple helper
        cfg = self.config_manager.config
        # RetryPolicy.from_cfg теперь будет вызываться из импортированного класса RetryPolicy
        retry_policy_instance = (
            RetryPolicy.from_cfg(cfg.retry) if isinstance(cfg.retry, RetryConfig) else RetryPolicy()
        )
        return HttpSettings(
            timeout=cfg.timeout,
            connect_timeout=getattr(cfg.http, 'connect_timeout', 10),
            delay_between_requests=cfg.delay,
            retry=retry_policy_instance, 
            use_proxy=cfg.use_proxy,
            max_connections=getattr(cfg.http, 'max_connections', 100),
            limit_per_host=getattr(cfg.http, 'limit_per_host', 10),
            keepalive_timeout=getattr(cfg.http, 'keepalive_timeout', 15),
        )

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            connector = TCPConnector(
                limit=self.settings.max_connections,
                limit_per_host=self.settings.limit_per_host,
                enable_cleanup_closed=True,
                keepalive_timeout=self.settings.keepalive_timeout,
            )
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=ClientTimeout(
                    total=self.settings.timeout,
                    connect=self.settings.connect_timeout,
                )
            )

    async def _wait_between_requests(self):
        now = asyncio.get_event_loop().time()
        since = now - self.last_request_time
        wait = self.settings.delay_between_requests - since
        if wait > 0:
            await asyncio.sleep(wait)
        self.last_request_time = asyncio.get_event_loop().time()

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> Optional[Union[str, Dict[str, Any], bytes]]:
        
        async def _fetch(m: str, u: str, **kwds_fetch):
            return await self._single_request(m, u, **kwds_fetch)

        chained_request_handler = _fetch
        for mw_instance in reversed(self.middlewares):
            def create_handler_stage(current_mw, next_in_chain):
                async def stage(method_stage: str, url_stage: str, **kwargs_stage):
                    return await current_mw(next_in_chain, method_stage, url_stage, **kwargs_stage)
                return stage
            chained_request_handler = create_handler_stage(mw_instance, chained_request_handler)
        
        request_kwargs = kwargs.copy()
        timeout_val = request_kwargs.pop('timeout', None)

        if timeout_val is not None:
            if not isinstance(timeout_val, ClientTimeout):
                 request_kwargs['timeout'] = ClientTimeout(total=timeout_val)
            else:
                 request_kwargs['timeout'] = timeout_val
        
        return await chained_request_handler(method, url, **request_kwargs)

    async def _single_request(
        self,
        method: str,
        url: str,
        response_type: str = "text", # This is passed via kwargs from _request -> _fetch -> _single_request
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> Optional[Union[str, Dict[str, Any], bytes]]:
        await self._ensure_session()
        await self._wait_between_requests()

        req_headers = {
            "User-Agent": self.config_manager.config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if headers:
            req_headers.update(headers)
        
        final_kwargs = kwargs.copy()
        final_kwargs["headers"] = req_headers
        final_kwargs.pop("use_proxy", None) 
        
        actual_response_type = final_kwargs.pop('response_type', response_type)

        try:
            async with getattr(self.session, method.lower())(url, **final_kwargs) as resp:
                if resp.status != 200:
                    raise aiohttp.ClientResponseError(
                        request_info=resp.request_info,
                        history=resp.history,
                        status=resp.status,
                        message=f"Request failed: {resp.status} for url {url}",
                        headers=resp.headers
                    )
                if actual_response_type == "json":
                    return await resp.json()
                if actual_response_type == "bytes":
                    return await resp.read()
                return await resp.text()
        except aiohttp.ClientConnectorError as e:
            self.logger.error(f"Connection error for {url}: {e}")
            raise
        except aiohttp.ClientResponseError:
            raise
        except aiohttp.ClientError as e:
            self.logger.error(f"Client error for {url}: {e}")
            raise
        except asyncio.TimeoutError as e:
            self.logger.error(f"Timeout error for {url}: {e}")
            raise 