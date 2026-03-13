from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.routers import auth, bookings, clubs, matches, sports, users
from app.routers import matchmaking
from app.routers import webhooks_stripe

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="The Campus API", version="0.1.0")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(sports.router)
app.include_router(clubs.router)
app.include_router(bookings.router)
app.include_router(matches.router)
app.include_router(matchmaking.router)
app.include_router(webhooks_stripe.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
