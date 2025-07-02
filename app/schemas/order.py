from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderBase(BaseModel):
    symbol: str = Field(..., description="Trading pair symbol (e.g., BTC/USD)")
    side: OrderSide
    order_type: OrderType
    quantity: float = Field(..., gt=0, description="Order quantity")
    price: Optional[float] = Field(None, gt=0, description="Limit price (required for limit orders)")
    stop_price: Optional[float] = Field(None, gt=0, description="Stop price (for stop orders)")


class OrderCreate(OrderBase):
    pass


class OrderUpdate(BaseModel):
    quantity: Optional[float] = Field(None, gt=0)
    price: Optional[float] = Field(None, gt=0)
    stop_price: Optional[float] = Field(None, gt=0)


class OrderResponse(OrderBase):
    id: int
    user_id: int
    filled_quantity: float
    status: OrderStatus
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class OrderBookEntry(BaseModel):
    price: float
    total_quantity: float
    order_count: int

    class Config:
        from_attributes = True


class OrderBookResponse(BaseModel):
    symbol: str
    bids: List[OrderBookEntry]  # Buy orders (descending by price)
    asks: List[OrderBookEntry]  # Sell orders (ascending by price)
    timestamp: datetime


class TradeResponse(BaseModel):
    id: int
    symbol: str
    buy_order_id: int
    sell_order_id: int
    quantity: float
    price: float
    executed_at: datetime

    class Config:
        from_attributes = True


class OrderCancellationResponse(BaseModel):
    order_id: int
    status: str
    message: str


class OrderSummary(BaseModel):
    total_orders: int
    pending_orders: int
    filled_orders: int
    cancelled_orders: int 