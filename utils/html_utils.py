import re
from typing import Optional, List, Any

def clean_text(text: str) -> str:
    """
    Cleans text from extra spaces and line breaks.
    
    Args:
        text: The source text.
    Returns:
        The cleaned text.
    """
    if not text:
        return ""
    
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_price(text: str) -> Optional[float]:
    """
    Extracts a price from a text string.
    
    Args:
        text: Text containing the price.
    Returns:
        The price as a float, or None if the price cannot be found or parsed.
    """
    if not text:
        return None
    
    # Remove all non-numeric characters except for period and comma
    price_text = re.sub(r'[^\d.,]', '', text)
    
    price_text = price_text.replace(',', '.')
    
    # If multiple periods exist, assume the last one
    # todo: double check this part
    if price_text.count('.') > 1:
        parts = price_text.split('.')
        price_text = ''.join(parts[:-1]) + '.' + parts[-1]
            
    try:
        return float(price_text)
    except ValueError:
        return None

def extract(elements: List[Any], default: Any = None) -> Any:
    """
    Extracts the first element from a list or returns a default value.

    Args:
        elements: The list of elements.
        default: The default value to return if the list is empty.

    Returns:
        The first element or the default value.
    """
    return elements[0] if elements else default
