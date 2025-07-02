from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, Index
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from enum import Enum as PyEnum
from app.core.db import Base


class OrderType(PyEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderSide(PyEnum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(PyEnum):
    PENDING = "pending"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    symbol = Column(String, nullable=False, index=True)  # e.g., "BTC/USD"
    side = Column(Enum(OrderSide), nullable=False)
    order_type = Column(Enum(OrderType), nullable=False)
    quantity = Column(Float, nullable=False)
    filled_quantity = Column(Float, default=0.0)
    price = Column(Float, nullable=True)  # None for market orders
    stop_price = Column(Float, nullable=True)  # For stop orders
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Indexes for efficient order book queries
    __table_args__ = (
        Index('idx_symbol_side_price', 'symbol', 'side', 'price'),
        Index('idx_user_status', 'user_id', 'status'),
    )


class OrderBookEntry(Base):
    __tablename__ = "order_book_entries"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    side = Column(Enum(OrderSide), nullable=False)
    price = Column(Float, nullable=False)
    total_quantity = Column(Float, default=0.0)
    order_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Composite index for efficient order book lookups
    __table_args__ = (
        Index('idx_symbol_side_price_unique', 'symbol', 'side', 'price', unique=True),
    )


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    buy_order_id = Column(Integer, nullable=False)
    sell_order_id = Column(Integer, nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    executed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_symbol_executed_at', 'symbol', 'executed_at'),
    ) 