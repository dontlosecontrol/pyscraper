import asyncio
import functools
import logging
from typing import Callable, TypeVar, Optional
from config.config_manager import ConfigManager

T = TypeVar('T')

logger = logging.getLogger(__name__)

#todo: Implement a "strategy" pattern here with exponential-random and linear-random delays


def async_retry(
    retries: int = 3,
    delay: float = 1.0,
    backoff_factor: Optional[float] = None,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
    config_manager: Optional[ConfigManager] = None
):
    """
    Decorator to retry an asynchronous function execution.

    Args:
        retries: Maximum number of retry attempts.
        delay: Initial delay between attempts in seconds.
        backoff_factor: Multiplier to increase the delay with each attempt. 
                        If None, it's taken from the config_manager if provided, 
                        otherwise defaults to 2.0.
        exceptions: A tuple of exception types that should be caught and retried.
        on_retry: Callback function invoked when a retry occurs.Receives the exception and current attempt number.
        config_manager: Optional ConfigManager to fetch backoff_factor if not explicitly set.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            if backoff_factor is None and config_manager is not None:
                current_backoff_factor = config_manager.config.backoff_factor
            else:
                current_backoff_factor = backoff_factor or 2.0 # todo: rework

            for attempt in range(retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt < retries:
                        if on_retry:
                            on_retry(e, attempt + 1)
                        else:
                            logger.warning(
                                f"Attempt {attempt + 1}/{retries} failed with error: {str(e)}. "
                                f"Retrying in {current_delay:.2f}s..."
                            )

                        await asyncio.sleep(current_delay)
                        current_delay *= current_backoff_factor
                    else:
                        logger.error(f"All {retries} retry attempts failed.")
                        raise

            if last_exception:
                raise last_exception

        return wrapper

    return decorator
