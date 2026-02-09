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
# NEW: Import from api.router (Showroom360 pattern)
from api.router.user import user_router as user_router_new
# Analytics router
from api.router.analytics import analytics_router
from api.router.search import search_router
from api.router.business import business_router as business_router_new
from api.router.savings import savings_router as savings_router_new
# OLD: Keep for backwards compatibility during migration
from api.router.payments import payments_router as payments_router_new
from api.router.expenses import expenses_router as expenses_router_new
from api.router.expenses import expenses_router as expenses_router_new
from api.router.financial_advisor import financial_advisor_router as financial_advisor_router_new
from api.router.cooperative import cooperative_router
from api.router.savings_group import router as savings_group_router

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
    "https://kopkad.onrender.com",  # Allow same-origin requests
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,  # Cache preflight requests for 1 hour
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
# NEW: Use new Showroom360-style router
app.include_router(user_router_new, prefix="/api/v1")
# Analytics endpoints
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
# OLD: Commented out - keeping for reference during migration
# app.include_router(user_router_old, prefix="/api/v1")
app.include_router(business_router_new, prefix="/api/v1")
app.include_router(savings_router_new, prefix="/api/v1")
app.include_router(payments_router_new, prefix="/api/v1")
app.include_router(expenses_router_new, prefix="/api/v1")
app.include_router(financial_advisor_router_new, prefix="/api/v1")
app.include_router(cooperative_router, prefix="/api/v1")
app.include_router(savings_group_router, prefix="/api/v1")

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
    
    # Initialize cache (Redis with in-memory fallback)
    try:
        from config.settings import settings as app_settings
        if app_settings.REDIS_URL:
            logger.info(f"Initializing cache from REDIS_URL")
            from urllib.parse import urlparse
            
            # Parse Redis URL (format: redis://host:port/db or redis://host:port)
            parsed = urlparse(app_settings.REDIS_URL)
            host = parsed.hostname or 'localhost'
            port = parsed.port or 6379
            db = int(parsed.path.lstrip('/')) if parsed.path and parsed.path != '/' else 0
            password = parsed.password
            
            # Try Redis, auto-fallback to in-memory if fails
            init_cache(host=host, port=port, db=db, password=password, fallback=True)
        else:
            # No Redis configured - use in-memory cache directly
            logger.info("ℹ️  REDIS_URL not configured - using in-memory cache")
            from utils.cache import InMemoryCache
            cache = InMemoryCache(maxsize=10000, ttl=300)
            from utils import cache as cache_module
            cache_module.cache = cache
    except Exception as e:
        logger.warning(f"⚠️  Cache initialization error: {e} - using in-memory fallback")
    
    # Test database connection
    try:
        # Test connection in an isolated block
        try:
            with engine.connect() as connection:
                result = connection.execute(text("SELECT current_database(), inet_server_addr(), inet_server_port()"))
                db_name, host, port = result.fetchone()
                logger.info(f"✓ Database connected: {db_name} at {host}:{port}")
            
            # Show connection pool status
            pool_status = get_connection_pool_status()
            logger.info(f"✓ Connection pool initialized: {pool_status}")
        except Exception as db_test_error:
            logger.warning(f"⚠️  Database connection test failed: {db_test_error}")
        
        # Bootstrap superadmin with a fresh session
        logger.info("Starting SUPER_ADMIN bootstrap process...")
        try:
            # Create a fresh session outside any transaction context
            from database.postgres_optimized import SessionLocal
            db = SessionLocal()
            try:
                bootstrap_super_admin(db)
                logger.info("✓ SUPER_ADMIN bootstrap completed")
            except Exception as bootstrap_error:
                logger.error(f"❌ Bootstrap error: {bootstrap_error}")
                import traceback
                logger.error(traceback.format_exc())
            finally:
                db.close()
        except Exception as session_error:
            logger.error(f"❌ Failed to create database session: {session_error}")
        
        # Initialize and start scheduler
        logger.info("Initializing Financial Advisor Scheduler...")
        init_scheduler()
        start_scheduler()
        logger.info("✓ Financial Advisor Scheduler started")
        
    except Exception as e:
        logger.error(f"❌ Error during startup: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        # Don't raise - allow app to start for health checks
    
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
    
    # Check cache (Redis or in-memory)
    try:
        from utils.cache import RedisCache, InMemoryCache
        cache_instance = get_cache()
        
        if isinstance(cache_instance, RedisCache):
            if cache_instance.enabled and cache_instance.ping():
                health["cache"] = "redis"
            else:
                health["cache"] = "redis-disconnected"
                health["status"] = "degraded"
        elif isinstance(cache_instance, InMemoryCache):
            health["cache"] = "in-memory"
            # In-memory is fine for single-server deployments
        else:
            health["cache"] = "none"
            health["status"] = "degraded"
    except Exception as e:
        health["cache"] = f"error: {str(e)}"
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