from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import auth, bookings, clubs, matches, sports, users
from app.routers import matchmaking

app = FastAPI(title="The Campus API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(sports.router)
app.include_router(clubs.router)
app.include_router(bookings.router)
app.include_router(matches.router)
app.include_router(matchmaking.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
