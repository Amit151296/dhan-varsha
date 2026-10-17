from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import LOG_LEVEL
from app.database import Base, engine
from app.logging_config import configure_logging
from app.routers import auth, screener

configure_logging(LOG_LEVEL)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Dhan Varsha API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(screener.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "Dhan Varsha API"}
