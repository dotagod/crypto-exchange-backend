import json
import asyncio
from typing import Dict, List, Optional
from fastapi import WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.routing import APIRouter

from app.services.trading_engine.redis_order_book import redis_order_book
from app.core.redis_config import redis_config
import redis.asyncio as redis_async

router = APIRouter()


class ConnectionManager:
    """Manage WebSocket connections for real-time updates with connection limits and pooling."""
    
    def __init__(self, 
                 max_connections_per_symbol: int = 1000, 
                 max_total_connections: int = 10000,
                 redis_pool_size: int = 100):
        self.max_connections_per_symbol = max_connections_per_symbol
        self.max_total_connections = max_total_connections
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.total_connections = 0
        self.redis_pool: Optional[redis_async.ConnectionPool] = None
        self.redis_client: Optional[redis_async.Redis] = None
        self._redis_connected = False
        self.redis_pool_size = redis_pool_size
        
        # Statistics tracking
        self.stats = {
            "total_connections": 0,
            "symbols_count": 0,
            "connections_per_symbol": {},
            "messages_sent": 0,
            "errors_count": 0
        }
    
    async def connect(self, websocket: WebSocket, symbol: str):
        """Connect a WebSocket for a specific symbol with connection limits."""
        # Check connection limits
        if self.total_connections >= self.max_total_connections:
            await websocket.close(code=1008, reason="Maximum total connections reached")
            return
        
        symbol_connections = len(self.active_connections.get(symbol, []))
        if symbol_connections >= self.max_connections_per_symbol:
            await websocket.close(code=1008, reason="Maximum connections for symbol reached")
            return
        
        await websocket.accept()
        
        if symbol not in self.active_connections:
            self.active_connections[symbol] = []
        
        self.active_connections[symbol].append(websocket)
        self.total_connections += 1
        
        # Update statistics
        self.stats["total_connections"] = self.total_connections
        self.stats["symbols_count"] = len(self.active_connections)
        self.stats["connections_per_symbol"][symbol] = len(self.active_connections[symbol])
        
        # Send initial order book snapshot
        try:
            order_book = redis_order_book.get_order_book(symbol, depth=20)
            await websocket.send_text(json.dumps({
                "type": "order_book_snapshot",
                "data": order_book
            }))
            self.stats["messages_sent"] += 1
        except Exception as e:
            # Send error message if order book unavailable
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": f"Failed to get order book: {str(e)}"
            }))
            self.stats["errors_count"] += 1
    
    def disconnect(self, websocket: WebSocket, symbol: str):
        """Disconnect a WebSocket and update statistics."""
        if symbol in self.active_connections:
            if websocket in self.active_connections[symbol]:
                self.active_connections[symbol].remove(websocket)
                self.total_connections -= 1
                
                # Update statistics
                self.stats["total_connections"] = self.total_connections
                self.stats["connections_per_symbol"][symbol] = len(self.active_connections[symbol])
                
                if not self.active_connections[symbol]:
                    del self.active_connections[symbol]
                    self.stats["symbols_count"] = len(self.active_connections)
                    if symbol in self.stats["connections_per_symbol"]:
                        del self.stats["connections_per_symbol"][symbol]
    
    async def _send_to_connection(self, connection: WebSocket, message: dict) -> bool:
        """Send message to a single connection with error handling."""
        try:
            await connection.send_text(json.dumps(message))
            self.stats["messages_sent"] += 1
            return True
        except WebSocketDisconnect:
            return False
        except Exception as e:
            print(f"Error sending to WebSocket: {e}")
            self.stats["errors_count"] += 1
            return False
    
    async def broadcast_to_symbol(self, symbol: str, message: dict):
        """Broadcast message to all connections for a symbol using parallel execution."""
        if symbol in self.active_connections:
            connections = self.active_connections[symbol].copy()
            
            # Create tasks for parallel sending
            tasks = [
                self._send_to_connection(connection, message)
                for connection in connections
            ]
            
            # Execute all sends in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Remove failed connections
            disconnected = []
            for i, result in enumerate(results):
                if result is False or isinstance(result, Exception):
                    disconnected.append(connections[i])
            
            # Remove disconnected connections
            for connection in disconnected:
                self.disconnect(connection, symbol)
    
    async def _ensure_redis_connection(self):
        """Ensure Redis connection pool is established."""
        if not self._redis_connected:
            try:
                # Create Redis connection pool
                self.redis_pool = redis_async.ConnectionPool.from_url(
                    redis_config.url if not redis_config.ssl else redis_config.ssl_url,
                    max_connections=self.redis_pool_size,
                    decode_responses=True
                )
                
                # Create Redis client with pool
                self.redis_client = redis_async.Redis(connection_pool=self.redis_pool)
                
                # Test connection
                await self.redis_client.ping()
                self._redis_connected = True
                print(f"✅ Redis connection pool established with {self.redis_pool_size} connections")
            except Exception as e:
                print(f"Failed to connect to Redis: {e}")
                self._redis_connected = False
                raise
    
    async def start_redis_listener(self):
        """Start listening to Redis pub/sub for order updates."""
        try:
            await self._ensure_redis_connection()
            
            if self.redis_client is None:
                raise ConnectionError("Redis client not available")
                
            pubsub = self.redis_client.pubsub()
            
            # Subscribe to order updates for all symbols
            await pubsub.psubscribe("order_updates:*")
            
            print("✅ Redis pub/sub listener started")
            
            async for message in pubsub.listen():
                if message["type"] == "pmessage":
                    symbol = message["channel"].split(":")[1]
                    data = json.loads(message["data"])
                    
                    # Broadcast to all connections for this symbol
                    await self.broadcast_to_symbol(symbol, {
                        "type": "order_update",
                        "data": data
                    })
                    
        except Exception as e:
            print(f"Redis listener error: {e}")
            self._redis_connected = False
            self.stats["errors_count"] += 1
        finally:
            if self.redis_client:
                await self.redis_client.close()
    
    def get_stats(self) -> dict:
        """Get current connection statistics."""
        return {
            "total_connections": self.total_connections,
            "max_total_connections": self.max_total_connections,
            "symbols_count": len(self.active_connections),
            "connections_per_symbol": self.stats["connections_per_symbol"].copy(),
            "messages_sent": self.stats["messages_sent"],
            "errors_count": self.stats["errors_count"],
            "redis_connected": self._redis_connected,
            "connection_utilization": {
                "total_percent": (self.total_connections / self.max_total_connections) * 100,
                "symbols": {
                    symbol: (len(conns) / self.max_connections_per_symbol) * 100
                    for symbol, conns in self.active_connections.items()
                }
            }
        }
    
    def reset_stats(self):
        """Reset message and error statistics."""
        self.stats["messages_sent"] = 0
        self.stats["errors_count"] = 0


# Global connection manager with optimized settings
manager = ConnectionManager(
    max_connections_per_symbol=1000,
    max_total_connections=10000,
    redis_pool_size=100
)


@router.websocket("/ws/orderbook/{symbol}")
async def websocket_orderbook(websocket: WebSocket, symbol: str):
    """WebSocket endpoint for real-time order book updates."""
    await manager.connect(websocket, symbol)
    
    try:
        while True:
            # Keep connection alive and handle any client messages
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle client requests
            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                manager.stats["messages_sent"] += 1
            elif message.get("type") == "get_order_book":
                try:
                    depth = message.get("depth", 10)
                    order_book = redis_order_book.get_order_book(symbol, depth)
                    await websocket.send_text(json.dumps({
                        "type": "order_book_update",
                        "data": order_book
                    }))
                    manager.stats["messages_sent"] += 1
                except Exception as e:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Failed to get order book: {str(e)}"
                    }))
                    manager.stats["errors_count"] += 1
            elif message.get("type") == "get_recent_trades":
                try:
                    limit = message.get("limit", 50)
                    trades = redis_order_book.get_recent_trades(symbol, limit)
                    await websocket.send_text(json.dumps({
                        "type": "recent_trades",
                        "data": [trade.to_dict() for trade in trades]
                    }))
                    manager.stats["messages_sent"] += 1
                except Exception as e:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Failed to get trades: {str(e)}"
                    }))
                    manager.stats["errors_count"] += 1
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, symbol)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.stats["errors_count"] += 1
        manager.disconnect(websocket, symbol)


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Test Redis connection
        if redis_order_book.ping():
            return {"status": "healthy", "redis": "connected"}
        else:
            return {"status": "degraded", "redis": "disconnected"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Redis connection failed: {str(e)}"
        )


@router.get("/stats")
async def get_connection_stats():
    """Get WebSocket connection statistics."""
    return manager.get_stats()


@router.post("/stats/reset")
async def reset_stats():
    """Reset message and error statistics."""
    manager.reset_stats()
    return {"message": "Statistics reset successfully"}


# Background task to start Redis listener when needed
async def start_redis_listener_task():
    """Background task to start Redis listener."""
    while True:
        try:
            await manager.start_redis_listener()
        except Exception as e:
            print(f"Redis listener failed, retrying in 5 seconds: {e}")
            manager.stats["errors_count"] += 1
            await asyncio.sleep(5)


# Background task will be started from main app startup 