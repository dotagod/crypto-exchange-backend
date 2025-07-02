from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import heapq
from collections import defaultdict


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


@dataclass
class OrderBookEntry:
    price: float
    total_quantity: float
    order_count: int
    orders: List[Order] = field(default_factory=list)


@dataclass
class Trade:
    id: int
    symbol: str
    buy_order_id: int
    sell_order_id: int
    quantity: float
    price: float
    executed_at: datetime = field(default_factory=datetime.utcnow)


class OrderBook:
    """
    In-memory order book implementation using Python objects.
    Uses heaps for efficient price level management.
    """
    
    def __init__(self):
        # Order storage
        self.orders: Dict[int, Order] = {}
        self.next_order_id = 1
        self.next_trade_id = 1
        
        # Order book by symbol
        # bids: max heap (negative prices for max heap behavior)
        # asks: min heap (positive prices)
        self.order_books: Dict[str, Dict[str, List[Tuple[float, float]]]] = defaultdict(
            lambda: {"bids": [], "asks": []}
        )
        
        # Price level details by symbol
        self.price_levels: Dict[str, Dict[str, Dict[float, OrderBookEntry]]] = defaultdict(
            lambda: {"bids": {}, "asks": {}}
        )
        
        # Trades by symbol
        self.trades: Dict[str, List[Trade]] = defaultdict(list)
    
    def add_order(self, user_id: int, symbol: str, side: OrderSide, 
                  order_type: OrderType, quantity: float, 
                  price: Optional[float] = None, stop_price: Optional[float] = None) -> Order:
        """Add a new order to the order book."""
        order = Order(
            id=self.next_order_id,
            user_id=user_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price
        )
        
        self.next_order_id += 1
        self.orders[order.id] = order
        
        # Add to order book if it's a limit order
        if order_type == OrderType.LIMIT and price:
            self._add_to_order_book(order)
        
        # Try to match the order
        self._match_order(order)
        
        return order
    
    def cancel_order(self, order_id: int, user_id: int) -> Order:
        """Cancel an order."""
        if order_id not in self.orders:
            raise ValueError("Order not found")
        
        order = self.orders[order_id]
        if order.user_id != user_id:
            raise ValueError("Order does not belong to user")
        
        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED]:
            raise ValueError(f"Cannot cancel order with status: {order.status}")
        
        order.status = OrderStatus.CANCELLED
        order.updated_at = datetime.utcnow()
        
        # Remove from order book if it was a limit order
        if order.order_type == OrderType.LIMIT and order.price:
            self._remove_from_order_book(order)
        
        return order
    
    def get_order(self, order_id: int, user_id: int) -> Order:
        """Get a specific order."""
        if order_id not in self.orders:
            raise ValueError("Order not found")
        
        order = self.orders[order_id]
        if order.user_id != user_id:
            raise ValueError("Order does not belong to user")
        
        return order
    
    def get_user_orders(self, user_id: int, status: Optional[OrderStatus] = None) -> List[Order]:
        """Get orders for a specific user."""
        user_orders = [order for order in self.orders.values() if order.user_id == user_id]
        
        if status:
            user_orders = [order for order in user_orders if order.status == status]
        
        return sorted(user_orders, key=lambda x: x.created_at, reverse=True)
    
    def get_order_book(self, symbol: str, depth: int = 10) -> Dict:
        """Get the order book for a specific symbol."""
        bids = []
        asks = []
        
        # Get bids (buy orders) - descending by price
        bid_heap = self.order_books[symbol]["bids"].copy()
        for _ in range(min(depth, len(bid_heap))):
            if bid_heap:
                price, _ = heapq.heappop(bid_heap)
                entry = self.price_levels[symbol]["bids"].get(-price)  # Convert back from negative
                if entry:
                    bids.append({
                        "price": entry.price,
                        "total_quantity": entry.total_quantity,
                        "order_count": entry.order_count
                    })
        
        # Get asks (sell orders) - ascending by price
        ask_heap = self.order_books[symbol]["asks"].copy()
        for _ in range(min(depth, len(ask_heap))):
            if ask_heap:
                price, _ = heapq.heappop(ask_heap)
                entry = self.price_levels[symbol]["asks"].get(price)
                if entry:
                    asks.append({
                        "price": entry.price,
                        "total_quantity": entry.total_quantity,
                        "order_count": entry.order_count
                    })
        
        return {
            "symbol": symbol,
            "bids": bids,
            "asks": asks,
            "timestamp": datetime.utcnow()
        }
    
    def get_recent_trades(self, symbol: str, limit: int = 50) -> List[Trade]:
        """Get recent trades for a symbol."""
        trades = self.trades.get(symbol, [])
        return sorted(trades, key=lambda x: x.executed_at, reverse=True)[:limit]
    
    def _add_to_order_book(self, order: Order):
        """Add a limit order to the order book."""
        side_key = "bids" if order.side == OrderSide.BUY else "asks"
        price = order.price
        
        if side_key not in self.price_levels[order.symbol]:
            self.price_levels[order.symbol][side_key] = {}
        
        if price not in self.price_levels[order.symbol][side_key]:
            # Create new price level
            entry = OrderBookEntry(
                price=price,
                total_quantity=order.quantity,
                order_count=1,
                orders=[order]
            )
            self.price_levels[order.symbol][side_key][price] = entry
            
            # Add to heap
            heap_price = -price if order.side == OrderSide.BUY else price
            heapq.heappush(self.order_books[order.symbol][side_key], (heap_price, price))
        else:
            # Update existing price level
            entry = self.price_levels[order.symbol][side_key][price]
            entry.total_quantity += order.quantity
            entry.order_count += 1
            entry.orders.append(order)
    
    def _remove_from_order_book(self, order: Order):
        """Remove a limit order from the order book."""
        side_key = "bids" if order.side == OrderSide.BUY else "asks"
        price = order.price
        
        if price in self.price_levels[order.symbol][side_key]:
            entry = self.price_levels[order.symbol][side_key][price]
            entry.total_quantity -= order.quantity
            entry.order_count -= 1
            
            # Remove the specific order from the list
            entry.orders = [o for o in entry.orders if o.id != order.id]
            
            if entry.total_quantity <= 0 or entry.order_count <= 0:
                # Remove price level
                del self.price_levels[order.symbol][side_key][price]
                
                # Remove from heap (this is simplified - in production you'd want a more efficient approach)
                heap_price = -price if order.side == OrderSide.BUY else price
                self.order_books[order.symbol][side_key] = [
                    (p, pr) for p, pr in self.order_books[order.symbol][side_key] 
                    if pr != price
                ]
                heapq.heapify(self.order_books[order.symbol][side_key])
    
    def _match_order(self, order: Order):
        """Match an order against the order book."""
        if order.status != OrderStatus.PENDING:
            return
        
        opposite_side = OrderSide.SELL if order.side == OrderSide.BUY else OrderSide.BUY
        side_key = "asks" if order.side == OrderSide.BUY else "bids"
        
        remaining_quantity = order.quantity
        
        # Get matching orders
        if order.order_type == OrderType.MARKET:
            matching_orders = self._get_matching_orders(order.symbol, opposite_side, remaining_quantity)
        else:
            matching_orders = self._get_matching_orders_with_price(
                order.symbol, opposite_side, remaining_quantity, order.price, order.side
            )
        
        # Execute trades
        for matching_order in matching_orders:
            if remaining_quantity <= 0:
                break
            
            available_quantity = matching_order.quantity - matching_order.filled_quantity
            trade_quantity = min(remaining_quantity, available_quantity)
            trade_price = matching_order.price
            
            # Create trade record
            if order.side == OrderSide.BUY:
                buy_order_id = order.id
                sell_order_id = matching_order.id
            else:
                buy_order_id = matching_order.id
                sell_order_id = order.id
            
            trade = Trade(
                id=self.next_trade_id,
                symbol=order.symbol,
                buy_order_id=buy_order_id,
                sell_order_id=sell_order_id,
                quantity=trade_quantity,
                price=trade_price
            )
            self.next_trade_id += 1
            self.trades[order.symbol].append(trade)
            
            # Update order quantities
            order.filled_quantity += trade_quantity
            matching_order.filled_quantity += trade_quantity
            remaining_quantity -= trade_quantity
            
            # Update order statuses
            if order.filled_quantity >= order.quantity:
                order.status = OrderStatus.FILLED
            else:
                order.status = OrderStatus.PARTIAL
            
            if matching_order.filled_quantity >= matching_order.quantity:
                matching_order.status = OrderStatus.FILLED
                # Remove filled order from order book
                if matching_order.order_type == OrderType.LIMIT:
                    self._remove_from_order_book(matching_order)
            else:
                matching_order.status = OrderStatus.PARTIAL
            
            order.updated_at = datetime.utcnow()
            matching_order.updated_at = datetime.utcnow()
    
    def _get_matching_orders(self, symbol: str, side: OrderSide, quantity: float) -> List[Order]:
        """Get orders that can potentially match."""
        matching_orders = []
        side_key = "asks" if side == OrderSide.SELL else "bids"
        
        # Get all orders at this price level
        for price, entry in self.price_levels[symbol][side_key].items():
            for order in entry.orders:
                if (order.status in [OrderStatus.PENDING, OrderStatus.PARTIAL] and 
                    order.order_type == OrderType.LIMIT):
                    matching_orders.append(order)
        
        # Sort by price (ascending for asks, descending for bids)
        if side == OrderSide.SELL:
            matching_orders.sort(key=lambda x: x.price)
        else:
            matching_orders.sort(key=lambda x: x.price, reverse=True)
        
        return matching_orders
    
    def _get_matching_orders_with_price(self, symbol: str, side: OrderSide, quantity: float,
                                      price: float, order_side: OrderSide) -> List[Order]:
        """Get orders that can match at the specified price."""
        matching_orders = []
        side_key = "asks" if side == OrderSide.SELL else "bids"
        
        for level_price, entry in self.price_levels[symbol][side_key].items():
            # Check price condition
            if order_side == OrderSide.BUY:
                # Buy orders match with sell orders at or below the buy price
                if level_price > price:
                    continue
            else:
                # Sell orders match with buy orders at or above the sell price
                if level_price < price:
                    continue
            
            for order in entry.orders:
                if (order.status in [OrderStatus.PENDING, OrderStatus.PARTIAL] and 
                    order.order_type == OrderType.LIMIT):
                    matching_orders.append(order)
        
        # Sort by price (ascending for asks, descending for bids)
        if side == OrderSide.SELL:
            matching_orders.sort(key=lambda x: x.price)
        else:
            matching_orders.sort(key=lambda x: x.price, reverse=True)
        
        return matching_orders


# Global order book instance
order_book = OrderBook() 