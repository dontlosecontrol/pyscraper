from typing import Any, Dict, Optional, List

class ScraperError(Exception):
    pass

class ScraperBaseError(Exception):
    """Base class for all scraper-specific exceptions."""
    pass

class ConfigError(ScraperBaseError):
    """Exception related to configuration loading or validation."""
    def __init__(self, message=None, config_path=None, key=None):
        self.config_path = config_path
        self.key = key
        msg = message or "Configuration error"
        if config_path:
            msg += f" in {config_path}"
        if key:
            msg += f" for key {key}"
        super().__init__(msg)

class UnknownParserError(ScraperBaseError):
    """Raised when a requested parser name is not found."""
    def __init__(self, parser_name: str, available_parsers: List[str]):
        self.parser_name = parser_name
        self.available_parsers = available_parsers
        message = (
            f"Unknown parser: '{parser_name}'. "
            f"Available parsers: {', '.join(available_parsers)}"
        )
        super().__init__(message)

class ParserInitializationError(ScraperBaseError):
    """Raised when a parser fails to initialize."""
    pass

class DataExtractionError(ScraperBaseError):
    """Raised when data extraction from a webpage fails."""
    pass

class HttpError(ScraperBaseError):
    """Base class for HTTP related errors."""
    pass

class HttpClientError(HttpError):
    """General HTTP Client error."""
    def __init__(self, message: str, url: Optional[str] = None):
        self.url = url
        full_message = f"{message} (URL: {url})" if url else message
        super().__init__(full_message)

class HttpResponseError(HttpError):
    """Raised for non-2xx HTTP responses after retries."""
    def __init__(self, status_code: Optional[int], url: str, message: str = "", headers: Optional[Dict[str, Any]] = None):
        self.status_code = status_code
        self.url = url
        self.message = message
        self.headers = headers or {}
        error_message = f"HTTP Error {status_code} for URL: {url}. Message: {message}"
        super().__init__(error_message)

class StorageError(ScraperBaseError):
    """Exception related to data storage operations."""
    pass

class ProxyError(ScraperBaseError):
    """Exception related to proxy configuration or usage."""
    def __init__(self, message=None, proxy_url=None):
        self.proxy_url = proxy_url
        super().__init__(message or f"Proxy error with {proxy_url}")