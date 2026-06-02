from fastapi import APIRouter, HTTPException
from datetime import datetime
import time
from api.models.signal_models import BrokerConnectRequest, TradeExecutionRequest

router = APIRouter()
_active_broker = None


def _resp(data, t0):
    return {"success": True, "data": data,
            "meta": {"timestamp": datetime.utcnow().isoformat() + "Z",
                     "processing_time_ms": round((time.time() - t0) * 1000),
                     "version": "1.0.0"}, "errors": []}


@router.post("/connect")
async def connect_broker(request: BrokerConnectRequest):
    t0 = time.time()
    global _active_broker
    try:
        config = {"paper_trading": request.paper_trading}
        if request.broker == "alpaca":
            from broker.alpaca_client import AlpacaClient
            _active_broker = AlpacaClient(config)
        elif request.broker == "ibkr":
            from broker.ibkr_client import IBKRClient
            _active_broker = IBKRClient(config)
        elif request.broker == "bybit":
            from broker.bybit_client import BybitClient
            _active_broker = BybitClient(config)
        elif request.broker == "okx":
            from broker.okx_client import OKXClient
            _active_broker = OKXClient(config)
        else:
            raise ValueError(f"Broker no soportado: {request.broker}")
        await _active_broker.connect()
        return _resp({"broker": request.broker, "paper": request.paper_trading,
                      "connected": True}, t0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def get_positions():
    t0 = time.time()
    if not _active_broker:
        return _resp({"positions": [], "note": "No hay broker conectado"}, t0)
    try:
        positions = await _active_broker.get_positions()
        return _resp({"positions": [vars(p) for p in positions]}, t0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute")
async def execute_trade(request: TradeExecutionRequest):
    t0 = time.time()
    if not _active_broker:
        raise HTTPException(status_code=400, detail="No hay broker conectado")
    try:
        from broker.order_executor import OrderExecutor
        from core.risk_manager import RiskManager
        risk = RiskManager({"max_risk_per_trade": 0.01, "max_drawdown_halt": -0.15})
        acc = await _active_broker.get_account_info()
        executor = OrderExecutor(_active_broker, risk)
        result = await executor.execute_signal(
            symbol=request.symbol,
            direction=request.direction,
            entry_price=request.entry_price,
            stop_loss=request.stop_loss,
            position_size_pct=request.position_size_pct,
            equity=acc.equity,
            leverage=request.leverage,
            take_profit=request.take_profit,
            strategy_name=request.strategy_name,
        )
        return _resp(result, t0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/account")
async def get_account():
    t0 = time.time()
    if not _active_broker:
        return _resp({"note": "No hay broker conectado"}, t0)
    try:
        acc = await _active_broker.get_account_info()
        return _resp(vars(acc), t0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
