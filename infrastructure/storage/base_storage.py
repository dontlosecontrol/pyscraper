from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseStorage(ABC):
    """Base abstract class for data storage"""

    @abstractmethod
    async def save(self, data: List[Dict[str, Any]], filename: str) -> None:
        """
        Args:
            data: List of dictionaries with data
            filename: Filename or identifier for saving
        """
        pass
