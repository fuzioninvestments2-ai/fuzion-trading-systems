"""Servidor FastAPI principal — integración con FUZION Web."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from api.routes.regime import router as regime_router
from api.routes.options import router as options_router
from api.routes.backtest import router as backtest_router
from api.routes.signals import router as signals_router
from api.routes.broker import router as broker_router
from api.routes.health import router as health_router

app = FastAPI(
    title="FUZION Trading Systems API",
    version="1.0.0",
    description="Backend Python para FUZION Trading Platform",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://titan-trading-platfo-ufcgle.abacusai.app",
        "http://localhost:3000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(regime_router, prefix="/api/regime", tags=["Regime"])
app.include_router(options_router, prefix="/api/options", tags=["Options"])
app.include_router(backtest_router, prefix="/api/backtest", tags=["Backtest"])
app.include_router(signals_router, prefix="/api/signals", tags=["Signals"])
app.include_router(broker_router, prefix="/api/broker", tags=["Broker"])
app.include_router(health_router, prefix="/api/health", tags=["Health"])


if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
