from typing import Type, Dict
from core.base_scraper import BaseScraper

# Internal parser registry
_PARSER_REGISTRY: Dict[str, Dict] = {}

def register_parser_decorator(parser_type: str, description: str = ""):
    """
    Decorator for automatic registration of a parser in the internal registry
    Args:
        parser_type: Parser type (e.g., 'myshop')
        description: Parser description
    Returns:
        Decorator
    """
    def decorator(cls: Type[BaseScraper]):
        _PARSER_REGISTRY[parser_type] = {"class": cls, "description": description}
        return cls
    return decorator

def get_registered_parsers() -> Dict[str, Dict]:
    """
    Returns the internal parser registry
    """
    return _PARSER_REGISTRY 