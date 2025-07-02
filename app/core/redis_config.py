import os
from typing import Optional


class RedisConfig:
    """Redis configuration settings."""
    
    def __init__(self):
        self.host = os.getenv("REDIS_HOST", "redis")
        self.port = int(os.getenv("REDIS_PORT", "6379"))
        self.db = int(os.getenv("REDIS_DB", "0"))
        self.password = os.getenv("REDIS_PASSWORD")
        self.ssl = os.getenv("REDIS_SSL", "false").lower() == "true"
        self.max_connections = int(os.getenv("REDIS_MAX_CONNECTIONS", "10"))
        self.socket_timeout = int(os.getenv("REDIS_SOCKET_TIMEOUT", "5"))
        self.socket_connect_timeout = int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "5"))
    
    @property
    def url(self) -> str:
        """Get Redis connection URL."""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"
    
    @property
    def ssl_url(self) -> str:
        """Get Redis SSL connection URL."""
        if self.password:
            return f"rediss://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"rediss://{self.host}:{self.port}/{self.db}"
    
    def get_connection_kwargs(self) -> dict:
        """Get connection arguments for Redis client."""
        kwargs = {
            "host": self.host,
            "port": self.port,
            "db": self.db,
            "decode_responses": True,
            "max_connections": self.max_connections,
            "socket_timeout": self.socket_timeout,
            "socket_connect_timeout": self.socket_connect_timeout,
        }
        
        if self.password:
            kwargs["password"] = self.password
        
        if self.ssl:
            kwargs["ssl"] = True
            kwargs["ssl_cert_reqs"] = None
        
        return kwargs


# Global Redis configuration instance
redis_config = RedisConfig() 