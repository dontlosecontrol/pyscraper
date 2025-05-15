from typing import List, Dict, Any, Optional, Type
from urllib.parse import urljoin

from lxml import html
from pydantic import BaseModel

from utils.html_utils import extract_price, extract
from core.base_scraper import BaseScraper
from config.config_manager import ConfigManager
from parsers.parser_registry import register_parser_decorator


from core.exceptions import ScraperError
from infrastructure.http_client import HttpClient  # typing-only but lightweight
from infrastructure.storage.base_storage import BaseStorage  # typing-only

class KnifecenterConfig(BaseModel):
    """Knifecenter specific configurations."""
    base_url: str = 'https://www.knifecenter.com'
    items_per_page: int = 36

@register_parser_decorator('knifecenter', 'knifecenter.com parser')
class KnifecenterScraper(BaseScraper):
    config: KnifecenterConfig

    @property
    def parser_config_model(self) -> Type[KnifecenterConfig]:
        return KnifecenterConfig

    def __init__(self,
                 shop_name: str = "knifecenter",
                 config_manager: Optional[ConfigManager] = None,
                 http_client: Optional[HttpClient] = None,
                 storage: Optional[BaseStorage] = None,
                 ):
        """
        Args:
            shop_name: Shop name
            config_manager: Config manager
            http_client: HTTP client
            storage: Data storage
        """
        super().__init__(shop_name, config_manager, http_client, storage)

    async def parse_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Parse item"""
        sku = extract(item.xpath(".//div[@class='purchase-row']//a/@data-sku"))

        price_text = extract(item.xpath(".//span[@class='our_price']/text()"))
        price = extract_price(price_text)

        item_url = extract(item.xpath("./a[@class='product_name']/@href"))

        name = extract(item.xpath(".//a[@class='product_name']/div[not(contains(@class, 'image-container'))]/text()"))
        if item_url is not None:
            item_url = urljoin(self.config.base_url, item_url)

        return {
            "shop_name": self.shop_name,
            'name': name,
            'url': item_url,
            'sku': sku,
            'price_regular': price,
        }

    async def parse_page(self, html_content: str, url: str) -> List[Dict[str, Any]]:
        """
        Parse HTML content and extract items
        Args:
            html_content: HTML page content
            url: Page URL
        Returns:
            List of extracted items
        """
        tree = html.fromstring(html_content)
        return [await self.parse_item(node) for node in tree.xpath("//div[contains(@class, 'listing_item')]")]

    async def _handle_main_or_category_page(self, tree: html.HtmlElement, current_url: str) -> bool:
        """
        Handles main catalog page or a category page by extracting and processing sub-category URLs.
        Returns True if it was a main/category page and was processed, False otherwise.
        """
        # Main page (e.g., /knife.html) or category page - look for 'all' links
        category_or_sub_category_urls = tree.xpath("//a[@class='all']/@href")
        if category_or_sub_category_urls:
            full_urls = [urljoin(current_url, u) for u in category_or_sub_category_urls]
            self.logger.info(f"Found {len(full_urls)} category/sub-category links on {current_url}")
            for cat_url in full_urls:
                # Recursively call process_url for each found category/sub-category
                await self.process_url(cat_url)
            return True
        return False

    async def _handle_product_listing_page(self, tree: html.HtmlElement, current_url: str, content: str) -> None:
        """
        Handles a product listing page by extracting product URLs and processing pagination.
        """
        # Page with products - extract links to the products themselves
        product_urls = tree.xpath("//div[@class='grid-style1__item']/a/@href")
        if product_urls: # Ensure there are product URLs before attempting to join
            full_product_urls = [urljoin(current_url, u) for u in product_urls]
            self.logger.info(f"Found {len(full_product_urls)} product links on {current_url}")
            for prod_url in full_product_urls:
                await self.process_product_page(prod_url)

        # Pagination should always be processed for product listing pages
        await self.process_pagination(current_url, content)

    async def process_url(self, url: str) -> None:
        """
        Process a single URL: download, parse, and store results.
        Delegates to helper methods based on page content.
        Args:
            url: Page URL
        """
        self.logger.info(f"Processing URL: {url}")
        try:
            content = await self.get_page_content(url)
            if not content:
                self.logger.error(f"Failed to get content for {url}")
                return

            tree = html.fromstring(content)

            # Try to handle as a main catalog page or a category page first
            if await self._handle_main_or_category_page(tree, url):
                return # If it was a category page, its job is done

            # If not a category page, assume it's a product listing page (or a page leading to products)
            await self._handle_product_listing_page(tree, url, content)

        except Exception as e:
            self.logger.error(f"Error processing {url}: {str(e)}")

    async def process_product_page(self, url: str) -> None:
        """
        Process a single product page and extract item data
        Args:
            url: Product page URL
        """
        content = await self.get_page_content(url)
        if not content:
            self.logger.error(f"Failed to get product page: {url}")
            return
        items = await self.parse_page(content, url)
        await self.process_items(items)

    async def process_pagination(self, url: str, content: str) -> None:
        """
        Handles pagination on product pages
        Args:
            url: URL of the current page
            content: HTML code of the page
        """
        tree = html.fromstring(content)
        next_page = extract(tree.xpath("//a[@class='next']/@href"))
        if next_page:
            next_url = urljoin(url, next_page)
            self.logger.info(f"Found next page: {next_url}")
            await self.process_url(next_url) 