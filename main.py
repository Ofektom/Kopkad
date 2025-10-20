from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import logging
import os

# Import optimized components
from database.postgres_optimized import (
    engine, get_db, init_db, 
    get_connection_pool_status, 
    check_database_health
)
from utils.cache import init_cache, get_cache
from middleware.auth import AuditMiddleware
from middleware.caching import CachingMiddleware

# Import routers
from api.user import user_router
from api.business import business_router
from api.savings import savings_router
from api.payments import payment_router
from api.expenses import expenses_router
from api.financial_advisor import financial_advisor_router

# Import scripts
from scripts.bootstrap_super_admin import bootstrap_super_admin
from schemas.user import UserResponse
from schemas.business import BusinessResponse, UnitResponse

# Import scheduler
from utils.scheduler import init_scheduler, start_scheduler, shutdown_scheduler

from sqlalchemy import text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Rebuild Pydantic models before app initialization
logger.info("Rebuilding Pydantic schemas...")
try:
    UserResponse.model_rebuild()
    BusinessResponse.model_rebuild()
    UnitResponse.model_rebuild()
    logger.info("✓ Pydantic schemas rebuilt successfully")
except Exception as e:
    logger.error(f"Error rebuilding Pydantic schemas: {str(e)}")
    raise

# Initialize FastAPI app
app = FastAPI(
    title="Ofektom Savings System API",
    description="Optimized API with Redis caching and load balancing",
    version="2.0.0"
)

# Middleware - Order matters!
# 1. CORS (must be first)

origins = [
    "http://localhost:3000",
    "http://localhost:8080",
    "http://localhost:5173",
    "https://kopkad-frontend.vercel.app",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Caching Middleware
app.add_middleware(
    CachingMiddleware,
    ttl=60,  # Cache for 60 seconds
    exclude_paths=[
        '/api/v1/auth/login',
        '/api/v1/auth/signup',
        '/api/v1/auth/refresh',
        '/health',
        '/metrics',
    ]
)

# 3. Audit Middleware (last)
app.add_middleware(AuditMiddleware)

# Routers
app.include_router(user_router, prefix="/api/v1")
app.include_router(business_router, prefix="/api/v1")
app.include_router(savings_router, prefix="/api/v1")
app.include_router(payment_router, prefix="/api/v1")
app.include_router(expenses_router, prefix="/api/v1")
app.include_router(financial_advisor_router, prefix="/api/v1")

@app.on_event("startup")
async def on_startup():
    """
    Startup tasks:
    - Initialize Redis cache
    - Test database connection
    - Bootstrap super admin
    - Start scheduler
    """
    logger.info("=" * 60)
    logger.info("APPLICATION STARTING UP")
    logger.info("=" * 60)
    
    # Initialize Redis cache
    try:
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        redis_password = os.getenv('REDIS_PASSWORD', None)
        
        init_cache(host=redis_host, port=redis_port, password=redis_password)
        
        if get_cache().ping():
            logger.info(f"✓ Redis connected at {redis_host}:{redis_port}")
        else:
            logger.warning("⚠️  Redis not available - caching disabled")
    except Exception as e:
        logger.warning(f"⚠️  Redis initialization error: {e} - caching disabled")
    
    # Test database connection
    db = next(get_db())
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT current_database(), inet_server_addr(), inet_server_port()"))
            db_name, host, port = result.fetchone()
            logger.info(f"✓ Database connected: {db_name} at {host}:{port}")
        
        # Show connection pool status
        pool_status = get_connection_pool_status()
        logger.info(f"✓ Connection pool initialized: {pool_status}")
        
        # Bootstrap superadmin
        logger.info("Starting SUPER_ADMIN bootstrap process...")
        bootstrap_super_admin(db)
        logger.info("✓ SUPER_ADMIN bootstrap completed")
        
        # Initialize and start scheduler
        logger.info("Initializing Financial Advisor Scheduler...")
        init_scheduler()
        start_scheduler()
        logger.info("✓ Financial Advisor Scheduler started")
        
    except Exception as e:
        logger.error(f"❌ Error during startup: {str(e)}")
        # Don't raise - allow app to start for health checks
    finally:
        db.close()
    
    logger.info("=" * 60)
    logger.info("APPLICATION READY")
    logger.info("=" * 60)

@app.on_event("shutdown")
async def on_shutdown():
    """
    Shutdown tasks:
    - Stop scheduler
    - Close database connections
    - Cleanup resources
    """
    logger.info("Application shutting down...")
    
    try:
        shutdown_scheduler()
        logger.info("✓ Scheduler shutdown")
    except Exception as e:
        logger.error(f"Error during scheduler shutdown: {e}")
    
    try:
        from database.postgres_optimized import close_all_connections
        close_all_connections()
        logger.info("✓ Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")
    
    logger.info("Shutdown completed")

@app.get("/")
def read_root():
    """Root endpoint"""
    return {
        "name": "Ofektom Savings System API",
        "version": "2.0.0",
        "status": "operational",
        "features": [
            "Redis caching",
            "Connection pooling",
            "Load balancing ready",
            "Database query optimization",
            "Auto-scaling support"
        ]
    }


@app.get("/health")
def health_check():
    """
    Health check endpoint for load balancers
    
    Returns:
        dict: Health status
    """
    health = {
        "status": "healthy",
        "timestamp": time.time(),
    }
    
    # Check Redis
    try:
        if get_cache().ping():
            health["redis"] = "connected"
        else:
            health["redis"] = "disconnected"
            health["status"] = "degraded"
    except:
        health["redis"] = "error"
        health["status"] = "degraded"
    
    # Check Database
    try:
        db_health = check_database_health()
        health["database"] = db_health.get("status", "unknown")
        if db_health.get("status") != "healthy":
            health["status"] = "degraded"
    except:
        health["database"] = "error"
        health["status"] = "unhealthy"
    
    status_code = 200 if health["status"] in ["healthy", "degraded"] else 503
    return JSONResponse(content=health, status_code=status_code)


@app.get("/metrics")
def metrics():
    """
    Metrics endpoint for monitoring
    
    Returns:
        dict: System metrics
    """
    metrics_data = {
        "timestamp": time.time(),
    }
    
    # Database metrics
    try:
        pool_status = get_connection_pool_status()
        metrics_data["database"] = {
            "pool_size": pool_status.get("size", 0),
            "connections_checked_in": pool_status.get("checked_in", 0),
            "connections_checked_out": pool_status.get("checked_out", 0),
            "overflow": pool_status.get("overflow", 0),
            "total_connections": pool_status.get("total_connections", 0),
        }
    except Exception as e:
        metrics_data["database"] = {"error": str(e)}
    
    # Redis metrics
    try:
        cache = get_cache()
        if cache.enabled:
            # Get Redis info
            info = cache.client.info()
            metrics_data["redis"] = {
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "0"),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
            }
            
            # Calculate hit rate
            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            total = hits + misses
            if total > 0:
                metrics_data["redis"]["hit_rate"] = f"{(hits / total * 100):.2f}%"
        else:
            metrics_data["redis"] = {"status": "disabled"}
    except Exception as e:
        metrics_data["redis"] = {"error": str(e)}
    
    return metrics_data


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """
    Add response time header to all responses
    """
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = f"{process_time:.4f}"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv('PORT', 8001))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,  # Disable reload in production
        workers=1,  # Use 1 worker per instance, scale horizontally
        log_level="info",
        access_log=True,
    )