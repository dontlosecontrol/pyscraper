import aiofiles
import json
from typing import List, Dict, Any
from os import makedirs, path
from .base_storage import BaseStorage
from core.data_models import ProductItem
from infrastructure.storage.registry import StorageRegistry

@StorageRegistry.register('json')
class JsonStorage(BaseStorage):
    async def save(self, data: List[Dict[str, Any]], filename: str) -> None:
        """
        Saves data to a JSON file asynchronously
        Args:
            data: List of dictionaries with data
            filename: Filename for saving
        """
        if not data:
            return
        makedirs(path.dirname(path.abspath(filename)), exist_ok=True)
        # Get ProductItem fields for headers and order
        fieldnames = list(ProductItem.schema()['properties'].keys())
        # Convert all rows to the required format (only necessary fields, order as in ProductItem)
        filtered_data = []
        for row in data:
            filtered_row = {field: row.get(field, '') for field in fieldnames}
            filtered_data.append(filtered_row)
        async with aiofiles.open(filename, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(filtered_data, ensure_ascii=False, indent=2))

    async def close(self) -> None:
        pass 