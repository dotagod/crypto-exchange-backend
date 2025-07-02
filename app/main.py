from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import time
import logging

from app.core.db import persistent_engine, Base
from app.routes import auth, user, order, market, websocket

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables (only persistent tables for users, wallets)
Base.metadata.create_all(bind=persistent_engine)

# Create FastAPI app
app = FastAPI(
    title="Crypto Exchange API",
    description="A production-grade crypto exchange backend API with in-memory order book",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Process Time: {process_time:.4f}s"
    )
    
    return response


# Include routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(user.router, prefix="/api/v1")
app.include_router(order.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(websocket.router, prefix="/api/v1")


@app.on_event("startup")
async def startup_event():
    """Start background tasks on application startup."""
    import asyncio
    from app.routes.websocket import start_redis_listener_task
    
    # Start Redis listener with delay to allow Redis to be ready
    async def delayed_start():
        await asyncio.sleep(5)  # Wait 5 seconds for Redis to be ready
        asyncio.create_task(start_redis_listener_task())
    
    asyncio.create_task(delayed_start())


@app.get("/")
async def root():
    return {
        "message": "Crypto Exchange API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 