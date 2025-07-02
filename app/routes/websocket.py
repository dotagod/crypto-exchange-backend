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
    """Manage WebSocket connections for real-time updates."""
    
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.redis_client: Optional[redis_async.Redis] = None
        self._redis_connected = False
    
    async def connect(self, websocket: WebSocket, symbol: str):
        """Connect a WebSocket for a specific symbol."""
        await websocket.accept()
        
        if symbol not in self.active_connections:
            self.active_connections[symbol] = []
        
        self.active_connections[symbol].append(websocket)
        
        # Send initial order book snapshot
        try:
            order_book = redis_order_book.get_order_book(symbol, depth=20)
            await websocket.send_text(json.dumps({
                "type": "order_book_snapshot",
                "data": order_book
            }))
        except Exception as e:
            # Send error message if order book unavailable
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": f"Failed to get order book: {str(e)}"
            }))
    
    def disconnect(self, websocket: WebSocket, symbol: str):
        """Disconnect a WebSocket."""
        if symbol in self.active_connections:
            self.active_connections[symbol].remove(websocket)
            if not self.active_connections[symbol]:
                del self.active_connections[symbol]
    
    async def broadcast_to_symbol(self, symbol: str, message: dict):
        """Broadcast message to all connections for a symbol."""
        if symbol in self.active_connections:
            disconnected = []
            for connection in self.active_connections[symbol]:
                try:
                    await connection.send_text(json.dumps(message))
                except WebSocketDisconnect:
                    disconnected.append(connection)
                except Exception as e:
                    print(f"Error broadcasting to WebSocket: {e}")
                    disconnected.append(connection)
            
            # Remove disconnected connections
            for connection in disconnected:
                self.disconnect(connection, symbol)
    
    async def _ensure_redis_connection(self):
        """Ensure Redis connection is established."""
        if not self._redis_connected:
            try:
                self.redis_client = redis_async.from_url(
                    redis_config.url if not redis_config.ssl else redis_config.ssl_url,
                    decode_responses=True
                )
                # Test connection
                await self.redis_client.ping()
                self._redis_connected = True
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
        finally:
            if self.redis_client:
                await self.redis_client.close()


# Global connection manager
manager = ConnectionManager()


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
            elif message.get("type") == "get_order_book":
                try:
                    depth = message.get("depth", 10)
                    order_book = redis_order_book.get_order_book(symbol, depth)
                    await websocket.send_text(json.dumps({
                        "type": "order_book_update",
                        "data": order_book
                    }))
                except Exception as e:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Failed to get order book: {str(e)}"
                    }))
            elif message.get("type") == "get_recent_trades":
                try:
                    limit = message.get("limit", 50)
                    trades = redis_order_book.get_recent_trades(symbol, limit)
                    await websocket.send_text(json.dumps({
                        "type": "recent_trades",
                        "data": [trade.to_dict() for trade in trades]
                    }))
                except Exception as e:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Failed to get trades: {str(e)}"
                    }))
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, symbol)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket, symbol)


# Remove startup event handler from router level


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


# Background task to start Redis listener when needed
async def start_redis_listener_task():
    """Background task to start Redis listener."""
    while True:
        try:
            await manager.start_redis_listener()
        except Exception as e:
            print(f"Redis listener failed, retrying in 5 seconds: {e}")
            await asyncio.sleep(5)


# Background task will be started from main app startup 