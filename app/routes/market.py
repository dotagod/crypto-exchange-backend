from fastapi import APIRouter
from app.services.exchange.mock_exchange_service import mock_exchange

router = APIRouter(prefix="/market", tags=["market"])

@router.get("/prices")
def get_prices():
    """Get current prices for all coins from the mock exchange."""
    return mock_exchange.get_prices() 