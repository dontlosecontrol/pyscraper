import random
import os
import logging
from typing import Optional, Dict, List, Any

class ProxyManager:
    
    def __init__(self, proxy_list: List[str] = None, proxy_file: str = None, max_requests_per_proxy: int = 10):
        """
        Initializes the proxy manager
        
        Args:
            proxy_list: List of proxy URLs
            proxy_file: Path to the proxy file
            max_requests_per_proxy: Maximum number of requests per proxy
        """
        self.logger = logging.getLogger(__name__)
        self.proxy_list = proxy_list or []
        self.current_proxy = None
        self.requests_with_current_proxy = 0
        self.max_requests_per_proxy = max_requests_per_proxy
        self.proxy_errors = {}  # Error counter for each proxy
        
        # Load proxies from file if specified
        if proxy_file and os.path.exists(proxy_file):
            self._load_proxies_from_file(proxy_file)
    
    def _load_proxies_from_file(self, proxy_file: str) -> None:
        """
        Loads proxies from a file
        
        Args:
            proxy_file: Path to the proxy file
        """
        try:
            with open(proxy_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    try:
                        # Format: user:pass@host:port
                        auth, address = line.split('@')
                        username, password = auth.split(':')
                        host, port_str = address.split(':')
                        
                        # Convert port to int 
                        try:
                            port = int(port_str)
                        except ValueError:
                            self.logger.error(f"Invalid port number: {port_str} in proxy: {line}")
                            continue
                        
                        proxy = {
                            'host': host,
                            'port': port,
                            'username': username,
                            'password': password
                        }
                        
                        self.proxy_list.append(proxy)
                    except Exception as e:
                        self.logger.error(f"Invalid proxy format: {line}, error: {str(e)}")
                        continue
            
            self.logger.info(f"Loaded {len(self.proxy_list)} proxies from {proxy_file}")
        except Exception as e:
            self.logger.error(f"Error loading proxies from {proxy_file}: {str(e)}")
    
    def get_random_proxy(self) -> Optional[Dict[str, Any]]:
        """
        Returns a random proxy from the list
        
        Returns:
            A random proxy or None if the list is empty
        """
        if not self.proxy_list:
            self.logger.warning("No proxies available")
            return None
        
        return random.choice(self.proxy_list)
    
    def should_change_proxy(self) -> bool:
        """
        Checks if the proxy needs to be changed
        
        Returns:
            True if the proxy needs to be changed
        """
        if self.current_proxy is None:
            return True
            
        if self.max_requests_per_proxy is not None:
            # If the request limit for the current proxy is reached
            if self.requests_with_current_proxy >= self.max_requests_per_proxy:
                return True
        
        # If the current proxy has too many errors
        proxy_key = str(self.current_proxy)
        if proxy_key in self.proxy_errors:
            if self.proxy_errors[proxy_key] >= 3:  # Maximum number of errors
                return True
        
        return False
    
    def prepare_proxy(self) -> Optional[Dict[str, Any]]:
        """
        Prepares a proxy for the request
        
        Returns:
            A dictionary with proxy parameters or None if no proxy is available
        """
        # Check if the proxy needs to be changed
        if self.should_change_proxy():
            self.current_proxy = self.get_random_proxy()
            self.requests_with_current_proxy = 0
            self.logger.debug(f"Switched to proxy: {self.current_proxy}")
        
        # Increment the request counter for the current proxy
        if self.current_proxy:
            self.requests_with_current_proxy += 1
        
        return self.current_proxy
    
    def report_error(self, error_type: str) -> None:
        """
        Registers a proxy error
        
        Args:
            error_type: Type of error (http, timeout, etc.)
        """
        if self.current_proxy:
            proxy_key = str(self.current_proxy)
            self.proxy_errors[proxy_key] = self.proxy_errors.get(proxy_key, 0) + 1
            self.logger.warning(f"Proxy error: {error_type} for {proxy_key}, errors: {self.proxy_errors[proxy_key]}")
            
            # If there are too many errors, reset the proxy
            if self.proxy_errors[proxy_key] >= 3:
                self.current_proxy = None
    
    def reset_state(self) -> None:
        """Resets the proxy state"""
        self.current_proxy = None
        self.requests_with_current_proxy = 0
        self.proxy_errors.clear()
