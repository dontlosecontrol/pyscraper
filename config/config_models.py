from typing import List, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

class RetryConfig(BaseModel):
    count: int = Field(default=3, ge=1)
    delay: float = Field(default=1.0, ge=0)
    backoff_factor: float = Field(default=2.0, ge=1)
    max_delay: float = Field(default=30.0, ge=0)
    status_codes: List[int] = Field(default_factory=lambda: [408, 429, 500, 502, 503, 504])


class ProxyConfig(BaseModel):
    list: List[str] = Field(default_factory=list)
    file: Optional[str] = Field(default=None) # "proxies.txt"


class StorageConfig(BaseModel):
    type: str = Field(default="csv")
    output_file: Optional[str] = Field(default=None)
    delay: float = Field(default=1.0, ge=0)


class HttpConfig(BaseModel):
    connect_timeout: int = Field(default=10, ge=1)
    max_connections: int = Field(default=100, ge=1)
    limit_per_host: int = Field(default=10, ge=1)
    keepalive_timeout: int = Field(default=15, ge=0)


class BatchConfig(BaseModel):
    # urls batch proessing
    size: int = Field(default=20, ge=1) 
    delay: float = Field(default=1.0, ge=0)


class DeduplicationConfig(BaseModel):
    primary_keys: List[str] = Field(default_factory=lambda: ["url", "sku"])


class ScraperConfig(BaseSettings):
    concurrency: int = Field(default=1, ge=1)
    sessions_count: int = Field(default=1, ge=1)
    delay: float = Field(default=1.0, ge=0)
    timeout: int = Field(default=30, ge=1)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    http: HttpConfig = Field(default_factory=HttpConfig)
    batch: BatchConfig = Field(default_factory=BatchConfig)
    user_agent: str = Field(default=(
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ))
    log_level: str = Field(default="INFO")
    log_file: Optional[str] = Field(default=None)
    max_requests_per_proxy: Optional[int] = Field(default=None)
    use_proxy: bool = Field(default=False)
    deduplication: DeduplicationConfig = Field(default_factory=DeduplicationConfig)

    model_config = {
        "extra": "allow",
        "env_prefix": "SCRAPER_",
        "case_sensitive": False,
    }
