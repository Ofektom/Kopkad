# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.user import user_router
from api.business import business_router
from api.savings import savings_router

# from api.deposits import deposit_router
# from api.expenses import expense_router
# from api.analytics import analytics_router
from api.payments import payment_router

# from api.notifications import notification_router
from middleware.auth import AuditMiddleware
from database.postgres import engine, Base, get_db
from scripts.bootstrap_super_admin import bootstrap_super_admin

app = FastAPI()

# Middleware
app.add_middleware(AuditMiddleware)

origins = ["http://localhost:3000", "http://localhost:8080","http://localhost:8001", "https://kopkad.onrender.com", ]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database tables
# Base.metadata.create_all(bind=engine)

# Routers
app.include_router(user_router, prefix="/api/v1")
app.include_router(business_router, prefix="/api/v1")
app.include_router(savings_router, prefix="/api/v1")
# app.include_router(deposit_router, prefix="/api/v1")
# app.include_router(expense_router, prefix="/api/v1")
# app.include_router(analytics_router, prefix="/api/v1")
app.include_router(payment_router, prefix="/api/v1")
# app.include_router(notification_router, prefix="/api/v1")


# Startup event to bootstrap SUPER_ADMIN
@app.on_event("startup")
def on_startup():
    print("Application starting up...")
    db = next(get_db())
    try:
        bootstrap_super_admin(db)
    except Exception as e:
        print(f"Error during bootstrap: {e}")
        # Don’t raise here to allow the app to start; handle gracefully
    finally:
        db.close()
        print("Startup process completed.")


@app.get("/")
def read_root():
    return {"Hello": "Welcome to Kopkad"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
