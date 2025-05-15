import os
import yaml
from typing import Dict, List, Optional, Any, Type
from copy import deepcopy
import datetime
from core.exceptions import ConfigError
from pydantic import ValidationError, BaseModel
import warnings
from .config_models import ScraperConfig




def _deep_update(base: Dict[str, Any], upd: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge *upd* dict into *base* dict and return new copy."""
    result = deepcopy(base)
    for k, v in upd.items():
        if (
            k in result
            and isinstance(result[k], dict)
            and isinstance(v, dict)
        ):
            result[k] = _deep_update(result[k], v)
        else:
            result[k] = deepcopy(v)
    return result


class ConfigManager:
    """Loads parser-specific YAML overrides, merges with ScraperConfig defaults, validates."""

    def __init__(self, shop_name: str, config_dir: str = "config"):
        """Initializes ConfigManager with new loading logic.

        Args:
            shop_name: Name of the shop, used to find overrides in parsers_config.yaml.
            config_dir: Directory containing configuration files (default: 'config').
        """
        self.shop_name = shop_name
        self.config_dir = config_dir
        # Path to the consolidated configuration file
        self.parsers_config_path = os.path.join(config_dir, "parsers_config.yaml")
        
        self._raw_parser_config_yaml: Dict[str, Any] = self._load_raw_parser_config_from_yaml()
        self.config: ScraperConfig = self._create_final_scraper_config(self._raw_parser_config_yaml)


    def update_config(self, **kwargs) -> None:
        """Update config in-memory, validating via pydantic."""
        current_config_dict = self.config.model_dump()
        updated_dict = _deep_update(current_config_dict, kwargs)
        try:
            self.config = ScraperConfig.model_validate(updated_dict)
        except ValidationError as e:
             raise ValueError(f"Configuration validation error during update: {e}") from e


    def finalize_runtime_settings(
        self,
        output_type_cli: Optional[str] = None,
        concurrency_cli: Optional[int] = None,
    ) -> None:
        """Applies CLI overrides, generates default filenames/log paths, and validates."""
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        parser_name = self.shop_name

        # Determine storage type: CLI > config > default ('csv')
        storage_type_from_config = self.config.storage.type
        final_storage_type = output_type_cli or storage_type_from_config # Default is already in ScraperConfig

        if final_storage_type not in ["csv", "json"]:
            raise ValueError(f"Invalid output_type: '{final_storage_type}'. Must be 'csv' or 'json'.")

        # Generate filename - use shop_name, date, and final type
        output_filename = f"{parser_name}_{current_date}.{final_storage_type}"
        # Generate log filename
        log_filename = f"{parser_name}_{current_date}.log"

        # Prepare updates dictionary
        updates: Dict[str, Any] = {
            "log_file": log_filename,
            # Update storage with potentially new type and the generated filename
            "storage": {"type": final_storage_type, "output_file": output_filename}
        }
        # Optional overrides from CLI
        if concurrency_cli is not None: # Check for None explicitly as 0 could be valid
            updates["concurrency"] = concurrency_cli

        try:
            self.update_config(**updates)
        except ValueError as e:
            raise ValueError(f"Configuration finalization error: {e}")


    # DI
    def create_http_client(self):  # noqa: D401 – simple factory
        """Return preconfigured *HttpClient* instance for current shop config."""
        # Lazy import to avoid heavy dependency at import time
        from infrastructure.http.client import HttpClient  # local import to prevent cycles

        return HttpClient(self)

    def create_http_clients(self, count: int | None = None):
        """Create `count` separate *HttpClient* instances (default sessions_count)."""
        if count is None:
            count = self.config.sessions_count
        return [self.create_http_client() for _ in range(count)]

    def create_storage(self):  # noqa: D401 – simple factory
        """Instantiate storage backend according to current *storage.type* option."""
        from infrastructure.storage.registry import StorageRegistry  # local import

        storage_type = self.config.storage.type # Get from validated config
        # Ensure concrete storage module is imported so that it registers itself
        import importlib

        try:
            importlib.import_module(f"infrastructure.storage.{storage_type}_storage")
        except ModuleNotFoundError:
            # No concrete module – will raise later in registry.get
            pass

        storage_cls = StorageRegistry.get(storage_type)
        return storage_cls()

    # todo: реализовать функционал
    def get_parser_specific_config(self, key: str, default: Any = None) -> Any:
        """Retrieve a parser-specific configuration value from the raw YAML config.

        This is useful for settings defined in parsers_config.yaml outside the
        standard ScraperConfig structure (e.g., CSS selectors, API endpoints).

        Args:
            key: The key of the configuration value to retrieve.
            default: The default value to return if the key is not found.

        Returns:
            The configuration value or the default.
        """
        return self._raw_parser_config_yaml.get(key, default)


    def get_parser_config(self, parser_config_model: Type[BaseModel]) -> BaseModel:
        """
        Creates and validates a parser-specific configuration model
        from the main configuration dictionary (self.config).
        """
        try:
            config_dict = self.config.model_dump(mode="python", exclude_none=True)
            return parser_config_model.model_validate(config_dict)
        except ValidationError as e:
            raise ConfigError(
                f"Validation error when creating specific config '{parser_config_model.__name__}' "
                f"for shop '{self.shop_name}': {e}"
            ) 
        
    def _load_raw_parser_config_from_yaml(self) -> Dict[str, Any]:
        """Loads the parser-specific section for the current shop from parsers_config.yaml."""
        all_parsers_data = self._read_yaml(self.parsers_config_path)

        if not all_parsers_data or "parsers" not in all_parsers_data:
            # If the file is empty or doesn't have 'parsers' key, return empty dict
            warnings.warn(f"'{self.parsers_config_path}' not found or missing 'parsers' key. Using default settings only.", UserWarning)
            return {}

        parser_specific_data = all_parsers_data["parsers"].get(self.shop_name, {})

        if not parser_specific_data:
             warnings.warn(f"No configuration section found for parser '{self.shop_name}' in '{self.parsers_config_path}'. Using default settings.", UserWarning)
             return {}
        if parser_specific_data is None:
            return {}

        return parser_specific_data

    def _create_final_scraper_config(self, parser_specific_config: Dict[str, Any]) -> ScraperConfig:
        """Builds the final ScraperConfig from defaults and provided parser-specific YAML config."""
        # 1. Start with default config from the model
        default_config = ScraperConfig()
        default_config_dict = default_config.model_dump()

        # 2. Deep merge overrides into defaults
        merged_config_dict = _deep_update(default_config_dict, parser_specific_config)

        # 3.Validate the merged configuration dictionary
        try:
            validated_config = ScraperConfig.model_validate(merged_config_dict)
        except ValidationError as e:
            raise ConfigError(f"Configuration validation failed for parser '{self.shop_name}' using '{self.parsers_config_path}': {e}") from e

        # 4.Handle proxy file loading (after validation)
        if validated_config.proxy and validated_config.proxy.file:
            proxy_file = validated_config.proxy.file
            if not os.path.isabs(proxy_file):
                proxy_file_path = os.path.join(self.config_dir, proxy_file)
            else:
                proxy_file_path = proxy_file

            if os.path.exists(proxy_file_path):
                loaded_proxies = self._load_proxies_from_file(proxy_file_path)
                existing_proxies = getattr(validated_config.proxy, 'list', []) or []
                validated_config.proxy.list = existing_proxies + loaded_proxies
            else:
                 warnings.warn(f"Proxy file specified but not found: {proxy_file_path}", UserWarning)

        return validated_config

    def _read_yaml(self, path: str) -> Optional[Dict[str, Any]]:
        """Safely read YAML file content."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            # File not found is handled upstream in _load_parser_overrides
            return None
        except (yaml.YAMLError, IOError) as e:
            raise ConfigError(f"Error reading YAML file {path}: {e}") from e

    @staticmethod
    def _load_proxies_from_file(file_path: str) -> List[str]:
        """Load proxies from plain-text file, ignoring commented/empty lines."""
        proxies: List[str] = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        proxies.append(line)
        except Exception as exc: 
            warnings.warn(f"Error loading proxies from file {file_path}: {exc}", UserWarning)
        return proxies
