from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import router as v1_router
from app.core.config import settings


# 1. Initialize FastAPI with metadata
app = FastAPI(
    title="Velocity AI Engine",
    description="ML & LLM orchestration service for project planning and resource analytics.",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc"
)

# 2. Configure CORS 
# Pulling origins from a centralized config is safer for production
origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://www.joinvelocity.co",
    "https://joinvelocity.co",
    "https://velocity-ai.joinvelocity.co",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Mount Versioned Routers
# This allows you to add /v2 later without breaking existing Node.js integrations
app.include_router(v1_router, prefix="/api/v1")

# 4. Global Health Check
@app.get("/", tags=["System"])
async def health_check():
    """
    Check if the ML Engine and Gemini connection are active.
    """
    return {
        "status": "online",
        "service": "velocity-python-ml-engine",
        "environment": "production" if not settings.DEBUG else "development"
    }

# 5. Startup/Shutdown Events (Optional)
@app.on_event("startup")
async def startup_event():
    # You can verify Supabase or Gemini connection here
    print("🚀 Velocity AI Engine starting up...")

@app.on_event("shutdown")
async def shutdown_event():
    print("💤 Velocity AI Engine shutting down...")