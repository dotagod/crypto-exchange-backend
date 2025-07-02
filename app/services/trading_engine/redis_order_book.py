import json
import time
from typing import Dict, List, Optional, Tuple, Union, Any
from datetime import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum
import redis
from decimal import Decimal, ROUND_HALF_UP

from app.core.redis_config import redis_config


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderStatus(Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"


@dataclass
class Order:
    id: int
    user_id: int
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    filled_quantity: float = 0.0
    price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert order to dictionary for Redis storage."""
        data = asdict(self)
        data['side'] = self.side.value
        data['order_type'] = self.order_type.value
        data['status'] = self.status.value
        data['created_at'] = self.created_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        
        # Remove None values as Redis doesn't accept them
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> 'Order':
        """Create order from dictionary from Redis."""
        # Handle missing optional fields
        if 'price' not in data:
            data['price'] = None
        if 'stop_price' not in data:
            data['stop_price'] = None
        if 'filled_quantity' not in data:
            data['filled_quantity'] = 0.0
            
        data['side'] = OrderSide(data['side'])
        data['order_type'] = OrderType(data['order_type'])
        data['status'] = OrderStatus(data['status'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        return cls(**data)


@dataclass
class Trade:
    id: int
    symbol: str
    buy_order_id: int
    sell_order_id: int
    quantity: float
    price: float
    executed_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert trade to dictionary for Redis storage."""
        data = asdict(self)
        data['executed_at'] = self.executed_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'Trade':
        """Create trade from dictionary from Redis."""
        data['executed_at'] = datetime.fromisoformat(data['executed_at'])
        return cls(**data)


class RedisOrderBook:
    """
    Redis-based order book implementation using advanced Redis features.
    
    Data Structure:
    - Sorted Sets (ZSET) for price levels: symbol:bids, symbol:asks
    - Lists for orders at each price level: symbol:bids:price, symbol:asks:price
    - Hashes for order details: order:order_id
    - Sets for user orders: user:user_id:orders
    - Streams for trade history: trades:symbol
    - Pub/Sub for real-time updates
    """
    
    def __init__(self, redis_url: Optional[str] = None, db: Optional[int] = None):
        self.redis_url = redis_url
        self.db = db
        self.redis: Optional[redis.Redis] = None
        self.pubsub: Optional[Any] = None  # redis.client.PubSub
        self._connected = False
        
        # Don't initialize counters here - do it lazily when first needed
    
    def _ensure_connection(self):
        """Ensure Redis connection is established."""
        if not self._connected:
            try:
                if self.redis_url:
                    self.redis = redis.from_url(self.redis_url, decode_responses=True)
                else:
                    # Use configuration
                    kwargs = redis_config.get_connection_kwargs()
                    if self.db is not None:
                        kwargs["db"] = self.db
                    self.redis = redis.Redis(**kwargs)
                
                self.pubsub = self.redis.pubsub()
                self._connected = True
                
                # Initialize counters only after successful connection
                self._init_counters()
                
            except Exception as e:
                raise ConnectionError(f"Failed to connect to Redis: {e}")
    
    def _init_counters(self):
        """Initialize order and trade ID counters."""
        if self.redis is None:
            raise ConnectionError("Redis connection not established")
            
        if not self.redis.exists("counters:order_id"):
            self.redis.set("counters:order_id", 0)
        if not self.redis.exists("counters:trade_id"):
            self.redis.set("counters:trade_id", 0)
    
    def _get_next_id(self, counter_key: str) -> int:
        """Get next ID atomically."""
        self._ensure_connection()
        if self.redis is None:
            raise ConnectionError("Redis connection not established")
        result = self.redis.incr(counter_key)
        return int(result) if result is not None else 0
    
    def _normalize_price(self, price: float) -> str:
        """Normalize price to 8 decimal places for consistent ordering."""
        return f"{Decimal(str(price)).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP):.8f}"
    
    def _get_price_key(self, symbol: str, side: OrderSide, price: float) -> str:
        """Get Redis key for price level."""
        side_str = "bids" if side == OrderSide.BUY else "asks"
        normalized_price = self._normalize_price(price)
        return f"{symbol}:{side_str}:{normalized_price}"
    
    def _get_order_book_key(self, symbol: str, side: OrderSide) -> str:
        """Get Redis key for order book sorted set."""
        side_str = "bids" if side == OrderSide.BUY else "asks"
        return f"{symbol}:{side_str}"
    
    def add_order(self, user_id: int, symbol: str, side: OrderSide, 
                  order_type: OrderType, quantity: float, 
                  price: Optional[float] = None, stop_price: Optional[float] = None) -> Order:
        """Add a new order to the order book using Redis pipeline for atomicity."""
        
        self._ensure_connection()
        if self.redis is None:
            raise ConnectionError("Redis connection not established")
        
        # Create order
        order_id = self._get_next_id("counters:order_id")
        order = Order(
            id=order_id,
            user_id=user_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price
        )
        
        # Use Redis pipeline for atomic operations
        pipe = self.redis.pipeline()
        
        try:
            # Store order details
            pipe.hset(f"order:{order_id}", mapping=order.to_dict())
            
            # Add to user's orders set
            pipe.sadd(f"user:{user_id}:orders", order_id)
            
            # Add to symbol orders set
            pipe.sadd(f"symbol:{symbol}:orders", order_id)
            
            # If it's a limit order, add to order book
            if order_type == OrderType.LIMIT and price is not None:
                self._add_to_order_book_pipeline(pipe, order)
            
            # Execute all operations atomically
            pipe.execute()
            
            # Try to match the order
            self._match_order(order)
            
            # Publish order update
            self._publish_order_update(order)
            
            return order
            
        except Exception as e:
            # Rollback on error
            if self.redis is not None:
                self.redis.delete(f"order:{order_id}")
                self.redis.srem(f"user:{user_id}:orders", order_id)
                self.redis.srem(f"symbol:{symbol}:orders", order_id)
            raise e
    
    def _add_to_order_book_pipeline(self, pipe, order: Order):
        """Add order to order book using pipeline."""
        if order.price is None:
            return
            
        price_key = self._get_price_key(order.symbol, order.side, order.price)
        order_book_key = self._get_order_book_key(order.symbol, order.side)
        
        # Add order to price level list (FIFO)
        pipe.lpush(price_key, order.id)
        
        # Add price to sorted set
        # For bids: use negative price for descending order (highest first)
        # For asks: use positive price for ascending order (lowest first)
        score = -order.price if order.side == OrderSide.BUY else order.price
        pipe.zadd(order_book_key, {str(order.price): score})
        
        # Update price level metadata
        pipe.hincrby(f"{price_key}:meta", "total_quantity", int(order.quantity * 100000000))  # Store as integer
        pipe.hincrby(f"{price_key}:meta", "order_count", 1)
    
    def cancel_order(self, order_id: int, user_id: int) -> Order:
        """Cancel an order."""
        self._ensure_connection()
        if self.redis is None:
            raise ConnectionError("Redis connection not established")
        
        # Get order details
        order_data = self.redis.hgetall(f"order:{order_id}")
        if not order_data:
            raise ValueError("Order not found")
        
        order = Order.from_dict(order_data)
        
        if order.user_id != user_id:
            raise ValueError("Order does not belong to user")
        
        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED]:
            raise ValueError(f"Cannot cancel order with status: {order.status}")
        
        # Update order status
        order.status = OrderStatus.CANCELLED
        order.updated_at = datetime.utcnow()
        
        pipe = self.redis.pipeline()
        
        # Update order in Redis
        pipe.hset(f"order:{order_id}", mapping=order.to_dict())
        
        # Remove from order book if it was a limit order
        if order.order_type == OrderType.LIMIT and order.price is not None:
            self._remove_from_order_book_pipeline(pipe, order)
        
        pipe.execute()
        
        # Publish order update
        self._publish_order_update(order)
        
        return order
    
    def _remove_from_order_book_pipeline(self, pipe, order: Order):
        """Remove order from order book using pipeline."""
        price_key = self._get_price_key(order.symbol, order.side, order.price)
        order_book_key = self._get_order_book_key(order.symbol, order.side)
        
        # Remove order from price level list
        pipe.lrem(price_key, 0, order.id)
        
        # Update price level metadata
        pipe.hincrby(f"{price_key}:meta", "total_quantity", -int(order.quantity * 100000000))
        pipe.hincrby(f"{price_key}:meta", "order_count", -1)
        
        # Check if price level is empty
        pipe.llen(price_key)
        pipe.hget(f"{price_key}:meta", "order_count")
        
        # Execute to get results
        results = pipe.execute()
        order_count = results[-1]
        
        if order_count == "0" or order_count == 0:
            # Remove empty price level
            pipe.delete(price_key, f"{price_key}:meta")
            pipe.zrem(order_book_key, str(order.price))
    
    def get_order(self, order_id: int, user_id: int) -> Order:
        """Get a specific order."""
        self._ensure_connection()
        
        order_data = self.redis.hgetall(f"order:{order_id}")
        if not order_data:
            raise ValueError("Order not found")
        
        order = Order.from_dict(order_data)
        if order.user_id != user_id:
            raise ValueError("Order does not belong to user")
        
        return order
    
    def get_user_orders(self, user_id: int, status: Optional[OrderStatus] = None) -> List[Order]:
        """Get orders for a specific user."""
        self._ensure_connection()
        
        order_ids = self.redis.smembers(f"user:{user_id}:orders")
        orders = []
        
        for order_id in order_ids:
            order_data = self.redis.hgetall(f"order:{order_id}")
            if order_data:
                order = Order.from_dict(order_data)
                if status is None or order.status == status:
                    orders.append(order)
        
        return sorted(orders, key=lambda x: x.created_at, reverse=True)
    
    def get_order_book(self, symbol: str, depth: int = 10) -> Dict:
        """Get the order book for a specific symbol."""
        self._ensure_connection()
        
        bids = []
        asks = []
        
        # Get bids (buy orders) - descending by price
        bid_prices = self.redis.zrevrange(f"{symbol}:bids", 0, depth - 1, withscores=True)
        for price_str, _ in bid_prices:
            price = float(price_str)
            price_key = self._get_price_key(symbol, OrderSide.BUY, price)
            meta = self.redis.hgetall(f"{price_key}:meta")
            
            if meta:
                bids.append({
                    "price": price,
                    "total_quantity": float(meta.get("total_quantity", 0)) / 100000000,
                    "order_count": int(meta.get("order_count", 0))
                })
        
        # Get asks (sell orders) - ascending by price
        ask_prices = self.redis.zrange(f"{symbol}:asks", 0, depth - 1, withscores=True)
        for price_str, _ in ask_prices:
            price = float(price_str)
            price_key = self._get_price_key(symbol, OrderSide.SELL, price)
            meta = self.redis.hgetall(f"{price_key}:meta")
            
            if meta:
                asks.append({
                    "price": price,
                    "total_quantity": float(meta.get("total_quantity", 0)) / 100000000,
                    "order_count": int(meta.get("order_count", 0))
                })
        
        return {
            "symbol": symbol,
            "bids": bids,
            "asks": asks,
            "timestamp": datetime.utcnow()
        }
    
    def get_recent_trades(self, symbol: str, limit: int = 50) -> List[Trade]:
        """Get recent trades for a symbol using Redis Streams."""
        self._ensure_connection()
        
        trades = []
        
        # Get recent trade IDs from stream
        stream_key = f"trades:{symbol}"
        messages = self.redis.xrevrange(stream_key, count=limit)
        
        for msg_id, fields in messages:
            trade_data = {k.decode() if isinstance(k, bytes) else k: 
                         v.decode() if isinstance(v, bytes) else v 
                         for k, v in fields.items()}
            trade = Trade.from_dict(trade_data)
            trades.append(trade)
        
        return trades
    
    def _match_order(self, order: Order):
        """Match an order against the order book using Lua script for atomicity."""
        if order.status != OrderStatus.PENDING:
            return
        
        # Lua script for atomic order matching
        lua_script = """
        local order_id = ARGV[1]
        local symbol = ARGV[2]
        local side = ARGV[3]
        local quantity = tonumber(ARGV[4])
        local price = tonumber(ARGV[5])
        local order_type = ARGV[6]
        
        local opposite_side = "asks"
        local order_book_key = symbol .. ":" .. opposite_side
        
        if side == "sell" then
            opposite_side = "bids"
            order_book_key = symbol .. ":" .. opposite_side
        end
        
        local remaining_quantity = quantity
        local trades = {}
        
        -- Get matching price levels
        local price_levels
        if side == "buy" then
            -- For buy orders, get asks in ascending order (lowest first)
            price_levels = redis.call('ZRANGE', order_book_key, 0, -1, 'WITHSCORES')
        else
            -- For sell orders, get bids in descending order (highest first)
            price_levels = redis.call('ZREVRANGE', order_book_key, 0, -1, 'WITHSCORES')
        end
        
        for i = 1, #price_levels, 2 do
            local level_price = price_levels[i]
            local score = price_levels[i + 1]
            
            -- Check price condition for limit orders
            if order_type == "limit" then
                if side == "buy" and tonumber(level_price) > price then
                    break
                elseif side == "sell" and tonumber(level_price) < price then
                    break
                end
            end
            
            local price_key = symbol .. ":" .. opposite_side .. ":" .. level_price
            local order_ids = redis.call('LRANGE', price_key, 0, -1)
            
            for _, matching_order_id in ipairs(order_ids) do
                if remaining_quantity <= 0 then
                    break
                end
                
                local order_data = redis.call('HGETALL', 'order:' .. matching_order_id)
                local order_dict = {}
                for j = 1, #order_data, 2 do
                    order_dict[order_data[j]] = order_data[j + 1]
                end
                
                local order_status = order_dict['status']
                if order_status == 'pending' or order_status == 'partial' then
                    local order_quantity = tonumber(order_dict['quantity'])
                    local filled_quantity = tonumber(order_dict['filled_quantity'])
                    local available_quantity = order_quantity - filled_quantity
                    
                    local trade_quantity = math.min(remaining_quantity, available_quantity)
                    
                    -- Create trade
                    local trade_id = redis.call('INCR', 'counters:trade_id')
                    local trade_data = {
                        id = trade_id,
                        symbol = symbol,
                        buy_order_id = side == "buy" and order_id or matching_order_id,
                        sell_order_id = side == "sell" and order_id or matching_order_id,
                        quantity = trade_quantity,
                        price = level_price,
                        executed_at = redis.call('TIME')[1]
                    }
                    
                    -- Add trade to stream
                    redis.call('XADD', 'trades:' .. symbol, '*', 
                              'id', trade_id,
                              'symbol', symbol,
                              'buy_order_id', trade_data.buy_order_id,
                              'sell_order_id', trade_data.sell_order_id,
                              'quantity', trade_quantity,
                              'price', level_price,
                              'executed_at', trade_data.executed_at)
                    
                    -- Update order quantities
                    redis.call('HINCRBY', 'order:' .. order_id, 'filled_quantity', trade_quantity)
                    redis.call('HINCRBY', 'order:' .. matching_order_id, 'filled_quantity', trade_quantity)
                    
                    remaining_quantity = remaining_quantity - trade_quantity
                    
                    -- Update order statuses
                    local new_filled = tonumber(redis.call('HGET', 'order:' .. order_id, 'filled_quantity'))
                    local order_qty = tonumber(redis.call('HGET', 'order:' .. order_id, 'quantity'))
                    if new_filled >= order_qty then
                        redis.call('HSET', 'order:' .. order_id, 'status', 'filled')
                    else
                        redis.call('HSET', 'order:' .. order_id, 'status', 'partial')
                    end
                    
                    local matching_filled = tonumber(redis.call('HGET', 'order:' .. matching_order_id, 'filled_quantity'))
                    local matching_qty = tonumber(redis.call('HGET', 'order:' .. matching_order_id, 'quantity'))
                    if matching_filled >= matching_qty then
                        redis.call('HSET', 'order:' .. matching_order_id, 'status', 'filled')
                        -- Remove filled order from order book
                        redis.call('LREM', price_key, 0, matching_order_id)
                    else
                        redis.call('HSET', 'order:' .. matching_order_id, 'status', 'partial')
                    end
                    
                    table.insert(trades, trade_id)
                end
            end
        end
        
        return {remaining_quantity, unpack(trades)}
        """
        
        # Execute Lua script
        result = self.redis.eval(lua_script, 0, 
                                order.id, order.symbol, order.side.value, 
                                order.quantity, order.price or 0, order.order_type.value)
        
        # Update order with remaining quantity
        if result[0] > 0:
            order.filled_quantity = order.quantity - result[0]
            order.status = OrderStatus.PARTIAL if order.filled_quantity > 0 else OrderStatus.FILLED
            self.redis.hset(f"order:{order.id}", mapping=order.to_dict())
    
    def _publish_order_update(self, order: Order):
        """Publish order update to Redis pub/sub."""
        update_data = {
            "order_id": order.id,
            "symbol": order.symbol,
            "side": order.side.value,
            "status": order.status.value,
            "quantity": order.quantity,
            "filled_quantity": order.filled_quantity,
            "price": order.price,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.redis.publish(f"order_updates:{order.symbol}", json.dumps(update_data))
    
    def subscribe_to_updates(self, symbol: str, callback):
        """Subscribe to real-time order book updates."""
        self._ensure_connection()
        self.pubsub.subscribe(f"order_updates:{symbol}")
        
        for message in self.pubsub.listen():
            if message['type'] == 'message':
                data = json.loads(message['data'])
                callback(data)
    
    def get_order_book_snapshot(self, symbol: str) -> Dict:
        """Get a complete snapshot of the order book."""
        return self.get_order_book(symbol, depth=1000)
    
    def clear_order_book(self, symbol: str):
        """Clear all orders for a symbol (for testing)."""
        self._ensure_connection()
        
        # Get all order IDs for the symbol
        order_ids = self.redis.smembers(f"symbol:{symbol}:orders")
        
        pipe = self.redis.pipeline()
        
        for order_id in order_ids:
            # Get order details
            order_data = self.redis.hgetall(f"order:{order_id}")
            if order_data:
                order = Order.from_dict(order_data)
                
                # Remove from user orders
                pipe.srem(f"user:{order.user_id}:orders", order_id)
                
                # Remove from order book if it's a limit order
                if order.order_type == OrderType.LIMIT and order.price:
                    price_key = self._get_price_key(order.symbol, order.side, order.price)
                    order_book_key = self._get_order_book_key(order.symbol, order.side)
                    
                    pipe.lrem(price_key, 0, order_id)
                    pipe.delete(price_key, f"{price_key}:meta")
                    pipe.zrem(order_book_key, str(order.price))
        
        # Remove symbol data
        pipe.delete(f"symbol:{symbol}:orders")
        pipe.delete(f"{symbol}:bids")
        pipe.delete(f"{symbol}:asks")
        pipe.delete(f"trades:{symbol}")
        
        pipe.execute()
    
    def ping(self) -> bool:
        """Test Redis connection."""
        try:
            self._ensure_connection()
            return self.redis.ping()
        except Exception:
            return False


# Global Redis order book instance - lazy initialization
redis_order_book = RedisOrderBook() 