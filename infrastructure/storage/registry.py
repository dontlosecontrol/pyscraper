from typing import Type, Dict

from infrastructure.storage.base_storage import BaseStorage

class StorageRegistry:
    _registry: Dict[str, Type[BaseStorage]] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator to register storage implementation by name."""
        def decorator(storage_cls: Type[BaseStorage]):
            cls._registry[name] = storage_cls
            return storage_cls
        return decorator

    @classmethod
    def get(cls, name: str) -> Type[BaseStorage]:
        if name not in cls._registry:
            raise KeyError(f"Storage '{name}' is not registered")
        return cls._registry[name] 