import inspect
from typing import Dict, Type

from core.base_scraper import BaseScraper
from core.exceptions import UnknownParserError
from config.config_manager import ConfigManager
from parsers.parser_registry import get_registered_parsers

# todo: get rid of manual parser adding
class ParserFactory:

    _parsers: Dict[str, Type[BaseScraper]] = None
    _descriptions: Dict[str, str] = None

    @classmethod
    def _ensure_initialized(cls):
        if cls._parsers is None or cls._descriptions is None:
            cls._parsers = {}
            cls._descriptions = {}
            for parser_type, meta in get_registered_parsers().items():
                cls._parsers[parser_type] = meta["class"]
                cls._descriptions[parser_type] = meta["description"]

    @classmethod
    def get_parser(cls, parser_type: str, config_manager: ConfigManager) -> BaseScraper:
        """
        Returns a parser instance of the specified type

        Args:
            parser_type: Parser type
            config_manager: Configuration manager

        Returns:
            Parser instance

        Raises:
            UnknownParserError: If the parser type is not supported
        """
        cls._ensure_initialized()
        if parser_type not in cls._parsers:
            raise UnknownParserError(parser_type, list(cls._parsers.keys()))

        parser_cls = cls._parsers[parser_type]
        try:
            return parser_cls(shop_name=parser_type, config_manager=config_manager)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize parser '{parser_type}': {e}") from e

    @classmethod
    def list_parsers(cls) -> Dict[str, str]:
        """
        Returns a list of available parsers

        Returns:
            A dictionary with parser types and their descriptions
        """
        cls._ensure_initialized()
        descriptions = {}
        for name, parser_cls in cls._parsers.items():
            docstring = inspect.getdoc(parser_cls)
            description = docstring.split('\n')[0] if docstring else "No description available."
            descriptions[name] = description
        return descriptions.copy()

    @classmethod
    def register_parser(cls, parser_type: str, parser_class: Type[BaseScraper], description: str = ""):
        """
        Registers a new parser in the factory
        Args:
            parser_type: Parser type (e.g., 'myshop')
            parser_class: Parser class
            description: Parser description
        """
        if parser_type in cls._parsers:
            raise ValueError(f"Parser '{parser_type}' is already registered.")
        if not issubclass(parser_class, BaseScraper):
            raise TypeError(f"{parser_class.__name__} must inherit from BaseScraper.")
        cls._parsers[parser_type] = parser_class
        if hasattr(cls, '_descriptions'):
            cls._descriptions[parser_type] = description
        else:
            cls._descriptions = {parser_type: description}