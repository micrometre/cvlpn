import os
from typing import Any, Callable

class ConfigLoader:
    """Enhanced configuration loader with type safety"""
    
    @staticmethod
    def get(key: str, default: Any = None, cast: Callable = str) -> Any:
        """Get config value with type conversion"""
        env_key = f"PLATE_{key.upper()}"
        value = os.environ.get(env_key, os.environ.get(key, default))
        
        if value is None:
            return default
            
        try:
            return cast(value)
        except (ValueError, TypeError) as e:
            logging.warning(f"Config conversion failed for {key}: {str(e)}")
            return default