from .base_storage import BaseStorage
from typing import List, Dict, Any

class DbStorage(BaseStorage):
    async def save(self, data: List[Dict[str, Any]], filename: str) -> None:
        """
        Stub for saving to DB
        """
        raise NotImplementedError("DbStorage.save is not implemented yet")

    async def close(self) -> None:
        pass
