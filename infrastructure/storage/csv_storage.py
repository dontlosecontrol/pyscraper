import csv
import aiofiles
from typing import List, Dict, Any
from os import makedirs, path
from .base_storage import BaseStorage
from core.data_models import ProductItem
from infrastructure.storage.registry import StorageRegistry

@StorageRegistry.register('csv')
class CsvStorage(BaseStorage):

    async def save(self, data: List[Dict[str, Any]], filename: str) -> None:
        """
        Args:
            data: List of dictionaries with data
            filename: Filename for saving
        """
        if not data:
            return

        # Create directory if it doesn't exist
        makedirs(path.dirname(path.abspath(filename)), exist_ok=True)

        # Get ProductItem fields for headers and order
        fieldnames = list(ProductItem.schema()['properties'].keys())

        # Convert all rows to the required format (only necessary fields, order as in ProductItem)
        filtered_data = []
        for row in data:
            filtered_row = {field: row.get(field, '') for field in fieldnames}
            filtered_data.append(filtered_row)

        # Optimized writing with buffering
        buffer_size = 1024 * 1024  # 1 MB
        buffer = []
        buffer_bytes = 0
        
        # Add header
        header = ';'.join(fieldnames) + '\n'
        buffer.append(header)
        buffer_bytes = len(header.encode('utf-8'))
        
        # Add data rows
        for item in filtered_data:
            row = []
            for field in fieldnames:
                value = item.get(field, '')
                # Escape special characters
                if isinstance(value, str) and any(c in value for c in [';', '"', '\n']):
                    value = f'"{value.replace('"', '""')}"'
                row.append(str(value))
            
            row_str = ';'.join(row) + '\n'
            row_bytes = len(row_str.encode('utf-8'))
            
            # If the buffer fills up after adding this row, write it first
            if buffer_bytes + row_bytes > buffer_size:
                async with aiofiles.open(filename, 'w' if buffer[0] == header else 'a', encoding='utf-8') as f:
                    await f.write(''.join(buffer))
                buffer = [row_str]
                buffer_bytes = row_bytes
            else:
                buffer.append(row_str)
                buffer_bytes += row_bytes
        
        # Write remaining data
        if buffer:
            async with aiofiles.open(filename, 'w' if buffer[0] == header else 'a', encoding='utf-8') as f:
                await f.write(''.join(buffer))

        #with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        #    writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=';')
        #    writer.writeheader()
        #    writer.writerows(data)

    async def close(self) -> None:
        pass
