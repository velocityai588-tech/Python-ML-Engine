from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import router as v1_router
from app.core.config import settings
from app.db.supabase import supabase  # Ensure this is imported

# 1. Initialize FastAPI with metadata
app = FastAPI(
    title="Velocity AI Engine",
    description="ML & LLM orchestration service for project planning and resource analytics.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 2. Configure CORS
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
app.include_router(v1_router, prefix="/api/v1")

# 4. Global Health Check
@app.get("/", tags=["System"])
async def health_check():
    return {
        "status": "online",
        "service": "velocity-python-ml-engine",
        "environment": "production" if not settings.DEBUG else "development"
    }

# 5. Startup/Shutdown Events
@app.on_event("startup")
async def startup_event():
    """
    Verify infrastructure availability on boot.
    """
    print("🚀 Velocity AI Engine starting up...")
    
    # Optional: Quick check for Supabase connectivity
    try:
        # Pinging a simple table to verify DB connection
        supabase.table("organizations").select("id").limit(1).execute()
        print("✅ Supabase connection verified.")
    except Exception as e:
        print(f"⚠️ Warning: Supabase connection failed: {e}")

    # Optional: Verify Gemini API configuration
    if not settings.GEMINI_API_KEY:
        print("❌ ERROR: GEMINI_API_KEY is missing from environment variables!")
    else:
        print("✅ Gemini API Key detected.")

@app.on_event("shutdown")
async def shutdown_event():
    print("💤 Velocity AI Engine shutting down...")