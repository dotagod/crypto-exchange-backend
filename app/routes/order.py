from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from typing import Optional, List

from app.core.security import get_current_user
from app.services.order.order_service import OrderService
from app.schemas.order import (
    OrderCreate, OrderResponse, OrderBookResponse, TradeResponse,
    OrderCancellationResponse, OrderSummary, OrderStatus
)

router = APIRouter(prefix="/orders", tags=["orders"])


def get_current_user_id(authorization: Optional[str] = Header(None)) -> int:
    """Get current user ID from JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = authorization.split(" ")[1]
    username = get_current_user(token)
    
    # For now, we'll use a simple approach to get user ID
    # In a real app, you'd store user ID in the token or query the database
    from app.core.db import get_persistent_db
    db = next(get_persistent_db())
    from app.services.user.user_service import UserService
    user_service = UserService(db)
    user = user_service.get_user_by_username(username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user.id


@router.post("/", response_model=OrderResponse)
def create_order(
    order_data: OrderCreate,
    user_id: int = Depends(get_current_user_id)
):
    """Create a new order."""
    order_service = OrderService()
    order = order_service.create_order(user_id, order_data)
    return order


@router.get("/", response_model=List[OrderResponse])
def get_user_orders(
    status: Optional[OrderStatus] = Query(None, description="Filter by order status"),
    user_id: int = Depends(get_current_user_id)
):
    """Get all orders for the current user."""
    order_service = OrderService()
    orders = order_service.get_user_orders(user_id, status)
    return orders


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    user_id: int = Depends(get_current_user_id)
):
    """Get a specific order by ID."""
    order_service = OrderService()
    order = order_service.get_order(order_id, user_id)
    return order


@router.delete("/{order_id}", response_model=OrderCancellationResponse)
def cancel_order(
    order_id: int,
    user_id: int = Depends(get_current_user_id)
):
    """Cancel an order."""
    order_service = OrderService()
    order = order_service.cancel_order(order_id, user_id)
    return OrderCancellationResponse(
        order_id=order_id,
        status="cancelled",
        message="Order cancelled successfully"
    )


@router.get("/book/{symbol}", response_model=OrderBookResponse)
def get_order_book(
    symbol: str,
    depth: int = Query(10, ge=1, le=100, description="Order book depth")
):
    """Get the order book for a specific symbol."""
    order_service = OrderService()
    order_book = order_service.get_order_book(symbol, depth)
    return order_book


@router.get("/trades/{symbol}", response_model=List[TradeResponse])
def get_recent_trades(
    symbol: str,
    limit: int = Query(50, ge=1, le=1000, description="Number of trades to return")
):
    """Get recent trades for a specific symbol."""
    order_service = OrderService()
    trades = order_service.get_recent_trades(symbol, limit)
    return trades


@router.get("/summary/", response_model=OrderSummary)
def get_order_summary(
    user_id: int = Depends(get_current_user_id)
):
    """Get order summary for the current user."""
    order_service = OrderService()
    
    all_orders = order_service.get_user_orders(user_id)
    pending_orders = order_service.get_user_orders(user_id, OrderStatus.PENDING)
    filled_orders = order_service.get_user_orders(user_id, OrderStatus.FILLED)
    cancelled_orders = order_service.get_user_orders(user_id, OrderStatus.CANCELLED)
    
    return OrderSummary(
        total_orders=len(all_orders),
        pending_orders=len(pending_orders),
        filled_orders=len(filled_orders),
        cancelled_orders=len(cancelled_orders)
    ) 