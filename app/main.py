from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import router

app = FastAPI(title="Velocity AI Engine", version="1.0")

# Allow your TSX Frontend to talk to this API
origins = [
    "http://localhost:3000",
    "http://localhost:5173", # Vite default
    "https://your-production-url.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")

@app.get("/")
def health_check():
    return {"status": "active", "service": "python-ml-engine"}