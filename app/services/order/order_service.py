from typing import List, Optional
from datetime import datetime
from fastapi import HTTPException, status

from app.services.trading_engine.redis_order_book import redis_order_book, OrderSide, OrderType, OrderStatus
from app.schemas.order import OrderCreate, OrderUpdate, OrderBookResponse, TradeResponse, OrderType as SchemaOrderType


class OrderService:
    def __init__(self):
        # Use Redis-based order book for persistence and scalability
        self.order_book = redis_order_book

    def create_order(self, user_id: int, order_data: OrderCreate) -> dict:
        """Create a new order and add it to the order book."""
        # Validate order data
        if order_data.order_type == SchemaOrderType.LIMIT and not order_data.price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Limit orders must have a price"
            )
        
        if order_data.order_type == SchemaOrderType.STOP and not order_data.stop_price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stop orders must have a stop price"
            )

        # Convert schema enums to order book enums
        side = OrderSide.BUY if order_data.side.value == "buy" else OrderSide.SELL
        order_type = OrderType(order_data.order_type.value)

        # Create the order using Redis order book
        order = self.order_book.add_order(
            user_id=user_id,
            symbol=order_data.symbol,
            side=side,
            order_type=order_type,
            quantity=order_data.quantity,
            price=order_data.price,
            stop_price=order_data.stop_price
        )
        
        return self._order_to_dict(order)

    def get_user_orders(self, user_id: int, status: Optional[OrderStatus] = None) -> List[dict]:
        """Get orders for a specific user."""
        orders = self.order_book.get_user_orders(user_id, status)
        return [self._order_to_dict(order) for order in orders]

    def get_order(self, order_id: int, user_id: int) -> dict:
        """Get a specific order by ID."""
        try:
            order = self.order_book.get_order(order_id, user_id)
            return self._order_to_dict(order)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )

    def cancel_order(self, order_id: int, user_id: int) -> dict:
        """Cancel an order."""
        try:
            order = self.order_book.cancel_order(order_id, user_id)
            return self._order_to_dict(order)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

    def get_order_book(self, symbol: str, depth: int = 10) -> OrderBookResponse:
        """Get the order book for a specific symbol."""
        order_book_data = self.order_book.get_order_book(symbol, depth)
        
        return OrderBookResponse(
            symbol=order_book_data["symbol"],
            bids=order_book_data["bids"],
            asks=order_book_data["asks"],
            timestamp=order_book_data["timestamp"]
        )

    def get_recent_trades(self, symbol: str, limit: int = 50) -> List[dict]:
        """Get recent trades for a symbol."""
        trades = self.order_book.get_recent_trades(symbol, limit)
        return [self._trade_to_dict(trade) for trade in trades]

    def _order_to_dict(self, order) -> dict:
        """Convert order object to dictionary."""
        return {
            "id": order.id,
            "user_id": order.user_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "quantity": order.quantity,
            "filled_quantity": order.filled_quantity,
            "price": order.price,
            "stop_price": order.stop_price,
            "status": order.status.value,
            "created_at": order.created_at,
            "updated_at": order.updated_at
        }

    def _trade_to_dict(self, trade) -> dict:
        """Convert trade object to dictionary."""
        return {
            "id": trade.id,
            "symbol": trade.symbol,
            "buy_order_id": trade.buy_order_id,
            "sell_order_id": trade.sell_order_id,
            "quantity": trade.quantity,
            "price": trade.price,
            "executed_at": trade.executed_at
        } 