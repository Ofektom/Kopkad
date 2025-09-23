from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.user import user_router
from api.business import business_router
from api.savings import savings_router
from api.payments import payment_router
from api.expenses import expenses_router
from middleware.auth import AuditMiddleware
from database.postgres import engine, get_db
from scripts.bootstrap_super_admin import bootstrap_super_admin
from schemas.user import UserResponse
from schemas.business import BusinessResponse, UnitResponse
from sqlalchemy import text
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rebuild Pydantic models before app initialization
logger.info("Rebuilding Pydantic schemas...")
try:
    UserResponse.model_rebuild()
    BusinessResponse.model_rebuild()
    UnitResponse.model_rebuild()
    logger.info("Pydantic schemas rebuilt successfully")
except Exception as e:
    logger.error(f"Error rebuilding Pydantic schemas: {str(e)}")
    raise

app = FastAPI()

# Middleware
app.add_middleware(AuditMiddleware)

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

# Routers
app.include_router(user_router, prefix="/api/v1")
app.include_router(business_router, prefix="/api/v1")
app.include_router(savings_router, prefix="/api/v1")
app.include_router(payment_router, prefix="/api/v1")
app.include_router(expenses_router, prefix="/api/v1")

# Startup event for database connection and superadmin bootstrap
@app.on_event("startup")
async def on_startup():
    logger.info("Application starting up...")
    db = next(get_db())
    try:
        # Test database connection
        with engine.connect() as connection:
            result = connection.execute(text("SELECT current_database(), inet_server_addr(), inet_server_port()"))
            db_name, host, port = result.fetchone()
            logger.info(f"Connected to database: {db_name} at {host}:{port}")

        # Bootstrap superadmin
        logger.info("Starting SUPER_ADMIN bootstrap process...")
        bootstrap_super_admin(db)
        logger.info("SUPER_ADMIN bootstrap completed successfully")
    except Exception as e:
        logger.error(f"Error during startup: {str(e)}")
        # Don’t raise to allow app to start
    finally:
        db.close()
        logger.info("Startup process completed.")

@app.get("/")
def read_root():
    return {"Hello": "Welcome to Kopkad"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)