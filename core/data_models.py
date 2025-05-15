from typing import Optional
from pydantic import BaseModel, Field
import datetime

class ProductItem(BaseModel):
    shop_name: str
    sku: Optional[str] = None
    name: str
    price_regular: float
    price_promo: Optional[float] = None
    scrape_time: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    url: str

    class Config:
        arbitrary_types_allowed = True
        extra = "ignore"
