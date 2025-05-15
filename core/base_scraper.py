import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Set, Callable, TypeVar, Type
import itertools
from contextlib import asynccontextmanager

from pydantic import BaseModel

from config.config_manager import ConfigManager
from infrastructure.http_client import HttpClient
from infrastructure.storage.base_storage import BaseStorage
from utils.logger_factory import get_scraper_logger

T = TypeVar('T')

class BaseScraper(ABC):
    config: BaseModel

    @property
    @abstractmethod
    def parser_config_model(self) -> Type[BaseModel]:
        """Abstract property that should return the Pydantic model for parser-specific config."""
        pass

    def __init__(self,
                 shop_name: str,
                 config_manager: ConfigManager,
                 http_client: Optional[HttpClient] = None,
                 storage: Optional[BaseStorage] = None):
        """Construct **BaseScraper**.

        Args:
            shop_name: Human-readable shop identifier.
            config_manager: Configuration manager with runtime settings.
            http_client: Pre-built HTTP client (or list of clients) to reuse.
            storage: Storage backend instance for persisting items.
        """
        self.shop_name = shop_name
        if config_manager is None:
            raise ValueError("ConfigManager instance must be provided to BaseScraper")
        self.config_manager = config_manager
        
        # Initialize list of HTTP clients and a cycle for round-robin
        if http_client is None:
            # Defer construction until asynchronous context to keep lazy behaviour
            self.http_clients = []
        elif isinstance(http_client, list):
            self.http_clients = http_client
        else:
            self.http_clients = [http_client]

        # Create iterator only if clients were already passed to the constructor
        self._client_cycle = None
        
        # Storage – inject or create via config manager
        self.storage = storage or self.config_manager.create_storage()
        self.results = []
        self.logger = get_scraper_logger(shop_name, self.config_manager)
        
        # New attributes for asynchronous work
        self._client_lock = asyncio.Lock()
        self._results_lock = asyncio.Lock()
        self._processed_urls: Set[str] = set()  # To track already processed URLs
        
        # Call method to initialize additional attributes
        self.initialize_attributes()
        
        self.logger.info(f"Initialized {self.__class__.__name__} with {self.config_manager.config.concurrency} concurrent tasks")
        self.logger.info(f"Will use {self.config_manager.config.sessions_count} HTTP sessions")
    
    def initialize_attributes(self):
        """Hook for child classes to attach extra attributes AND loads parser-specific config."""
        # Load parser-specific configuration
        try:
            self.config = self.config_manager.get_parser_config(self.parser_config_model)
        except Exception as e: # Catch ConfigError or other Pydantic validation issues
            # Log and re-raise as a ScraperError to be handled by the caller/main app loop
            self.logger.error(f"Failed to load parser-specific configuration for {self.shop_name}: {e}")
            # It's crucial that an error here stops scraper initialization.
            from core.exceptions import ScraperError # Local import to avoid circular dependency issues at module level
            raise ScraperError(f"Configuration load error for {self.shop_name}: {e}") from e
        pass

    async def _initialize_sessions(self) -> None:
        """Create HTTP-client pool according to config if it does not exist."""
        if self.http_clients:
            return
        self.logger.info("Initializing %s HTTP sessions", self.config_manager.config.sessions_count)
        # If pool already filled externally – respect it and do not duplicate
        if not self.http_clients:
            self.http_clients.extend(
                self.config_manager.create_http_clients(
                    self.config_manager.config.sessions_count
                )
            )
        # (Re)create round-robin iterator once pool ready
        self._client_cycle = itertools.cycle(self.http_clients)

    async def _close_sessions(self) -> None:
        """Close all HTTP sessions and attached storage (called from ``__aexit__``)."""
        self.logger.info("Closing sessions...")
        close_tasks = []
        for client in self.http_clients:
            close_tasks.append(client.close())
        
        if close_tasks:
            await asyncio.gather(*close_tasks)
            
        self.http_clients.clear()
        self._client_cycle = None
        if self.storage:
            await self.storage.close()
        self.logger.info("All sessions closed")

    async def get_http_client(self) -> HttpClient:
        """Return next HTTP client from round-robin pool.

        Returns:
            HTTP-client
        """
        if not self.http_clients or self._client_cycle is None:
            raise RuntimeError(
                "HTTP clients not initialized. Call initialize_session() first."
            )
            
        # Use lock for safe operation in asynchronous context
        async with self._client_lock:
            return next(self._client_cycle)
    
    @asynccontextmanager
    async def get_client_session(self):
        """Get an HTTP client from the pool as an async context manager.
        
        Usage:
            async with self.get_client_session() as client:
                html = await client.get(url)
        """
        client = await self.get_http_client()
        try:
            yield client
        finally:
            pass
    
    async def get_page_content(self, url: str, use_proxy: Optional[bool] = None, 
                              headers: Optional[Dict[str, str]] = None,
                              timeout: Optional[int] = None) -> Optional[str]:
        """Download raw HTML content.

        Args:
            url: Absolute page URL.
            use_proxy: Force proxy usage for this request (overrides global cfg).
            headers: Optional HTTP headers to send with request
            timeout: Optional timeout override for this specific request

        Returns:
            Raw HTML as string, or ``None`` on failure.
        """
        try:
            async with self.get_client_session() as client:
                return await client.get(url, use_proxy=use_proxy, headers=headers, timeout=timeout)
        except Exception as e:
            self.logger.error(f"Error getting page content for {url}: {str(e)}")
            return None

    @abstractmethod
    async def parse_page(self, html_content: str, url: str) -> List[Dict[str, Any]]:
        """Parse given HTML page and return list of product dictionaries."""
        pass
    
    async def transform_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Validate items, apply transformation pipeline and extend ``self.results``."""
        from core.data_models import ProductItem  # local import to avoid circular dependencies
        from pydantic import ValidationError

        # ensure mandatory "shop_name" present; prefer original value if already specified
        payload: Dict[str, Any] = {**item}
        payload.setdefault("shop_name", self.shop_name)

        try:
            validated = ProductItem.model_validate(payload)
        except ValidationError as exc:
            # Log and skip broken item
            self.logger.warning("Validation error for item %s: %s", item, exc)
            return None

        return validated.model_dump(mode="python")
    
    async def process_items(self, items: List[Dict[str, Any]]) -> None:
        """Validate items, apply transformation pipeline and extend ``self.results``."""
        if not items:
            return
            
        transform_tasks = [self.transform_item(item) for item in items]
        transformed_items = await asyncio.gather(*transform_tasks)
        
        # Filter None and add to results with lock
        valid_items = [item for item in transformed_items if item is not None]
        
        if valid_items:
            async with self._results_lock:
                self.results.extend(valid_items)
                self.logger.info(f"Added {len(valid_items)} items to results")

    async def process_url(self, url: str) -> None:
        """Scrape single URL – fetch, parse, transform and recurse if needed."""
        # Check if we have already processed this URL
        if url in self._processed_urls:
            self.logger.debug(f"Skipping already processed URL: {url}")
            return
            
        # Add URL to the list of processed ones
        self._processed_urls.add(url)
        
        self.logger.info(f"Processing URL: {url}")
        try:
            # Get page content
            content = await self.get_page_content(url)
            if not content:
                self.logger.error(f"Failed to get content for {url}")
                return
                
            # Parse page and process items
            items = await self.parse_page(content, url)
            await self.process_items(items)
            
            # Process pagination if the method is overridden in a subclass
            await self.process_pagination(url, content)
            
        except Exception as e:
            self.logger.error(f"Error processing {url}: {str(e)}")
    
    async def process_pagination(self, url: str, content: str) -> None:
        """Handle pagination – override in subclasses when necessary."""
        # Do nothing by default
        pass
    
    async def batch_process_urls(self, urls: List[str], batch_size: int = 10) -> None:
        """Process URLs in batches to limit memory usage."""
        for i in range(0, len(urls), batch_size):
            batch = urls[i:i+batch_size]
            self.logger.info(f"Processing batch {i//batch_size + 1}/{(len(urls) + batch_size - 1)//batch_size} " 
                            f"({len(batch)} URLs)")
            
            semaphore = asyncio.Semaphore(self.config_manager.config.concurrency)
            
            async def _process_with_semaphore(url: str):
                async with semaphore:
                    await self.process_url(url)
            
            tasks = [_process_with_semaphore(url) for url in batch]
            await asyncio.gather(*tasks)
            
            # Optional pause between batches to reduce load
            if i + batch_size < len(urls) and hasattr(self.config_manager.config.batch, 'delay'):
                await asyncio.sleep(self.config_manager.config.batch.delay)
    
    async def scrape_urls(self, urls: List[str]) -> None:
        """Scrape list of URLs concurrently respecting *concurrency* limit."""
        self.logger.info(f"Starting scraping {len(urls)} URLs with {self.config_manager.config.concurrency} concurrent tasks")
        self.logger.info(f"Using {len(self.http_clients)} HTTP sessions")
        
        # Use batch processing for large lists of URLs
        if len(urls) > 50 and hasattr(self.config_manager.config.batch, 'size'):
            await self.batch_process_urls(urls, self.config_manager.config.batch.size)
            return
        
        # For small lists, use the standard approach with a semaphore
        concurrency = self.config_manager.config.concurrency
        semaphore = asyncio.Semaphore(concurrency)

        async def _runner(single_url: str):
            async with semaphore:
                await self.process_url(single_url)

        # Start processing URLs asynchronously
        tasks = [_runner(url) for url in urls]
        await asyncio.gather(*tasks)
        
        self.logger.info(f"Finished scraping. Total items found: {len(self.results)}")

    def _remove_duplicates(self, items: List[Dict[str, Any]],
                         primary_keys: List[str] = None) -> List[Dict[str, Any]]:
        """Remove duplicates by *primary_keys* keeping the first occurrence."""
        if not items:
            return []

        # Use standard keys if others are not specified
        if not primary_keys:
            primary_keys = ["url", "article"]

        seen = set()
        unique_items = []

        for item in items:
            # Create key based on specified fields
            key_parts = []
            for key in primary_keys:
                key_parts.append(str(item.get(key, "")))

            key = "_".join(key_parts)

            # If key has been seen, skip item
            if key in seen:
                continue

            # If all checks passed, add item
            seen.add(key)
            unique_items.append(item)

        removed_count = len(items) - len(unique_items)
        if items:
             self.logger.info(f"Removed {removed_count} duplicate items ({removed_count / len(items) * 100:.1f}%)")
        else:
             self.logger.info(f"Removed {removed_count} duplicate items (0.0%)") # Or handle as appropriate
        return unique_items

    async def save_results(self, output_file: str) -> None:
        """Persist collected results via configured storage backend."""
        # Get filtering parameters from configuration, if they exist
        primary_keys = None

        try:
            # Check for filtering parameters in the configuration
            if hasattr(self.config_manager.config, 'deduplication'):
                dedup_config = self.config_manager.config.deduplication
                if hasattr(dedup_config, 'primary_keys') and dedup_config.primary_keys:
                    primary_keys = dedup_config.primary_keys
        except Exception as e:
            self.logger.warning(f"Error getting deduplication config, using defaults: {str(e)}")

        # Filter duplicates before saving
        filtered_results = self._remove_duplicates(
            self.results,
            primary_keys=primary_keys
        )

        self.logger.info(f"Saving {len(filtered_results)} items to {output_file}")
        # Storage is already created in __init__, type can be changed externally if needed
        await self.storage.save(filtered_results, output_file)
        self.logger.info(f"Results saved to {output_file}")
        
    async def execute_parallel(self, 
                             items: List[T], 
                             worker_func: Callable[[T], Any], 
                             max_workers: Optional[int] = None) -> List[Any]:
        """Execute a function across multiple items in parallel with concurrency control.
        
        Args:
            items: List of items to process
            worker_func: Async function that processes a single item
            max_workers: Maximum number of concurrent workers (defaults to config concurrency)
            
        Returns:
            List of results from worker function
        """
        if not items:
            return []
            
        concurrent_limit = max_workers or self.config_manager.config.concurrency
        semaphore = asyncio.Semaphore(concurrent_limit)
        
        async def _bounded_worker(item: T):
            async with semaphore:
                return await worker_func(item)
                
        return await asyncio.gather(*[_bounded_worker(item) for item in items])

    def _format_price(self, price: float) -> str:
        """Pretty-print price dropping trailing decimals when zero."""
        if not price:
            return None
        if price == int(price):
            return str(int(price))
        return str(price)

    async def __aenter__(self):
        """Initialize HTTP sessions and return self."""
        await self._initialize_sessions()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close HTTP sessions regardless of errors."""
        await self._close_sessions()

