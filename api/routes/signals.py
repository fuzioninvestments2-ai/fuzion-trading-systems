from fastapi import APIRouter, HTTPException
from datetime import datetime
import time
from api.models.signal_models import SignalRequest
from core.hmm_engine import HMMEngine
from core.regime_strategies import RegimeOrchestrator
from data.market_data import MarketData as MktData

router = APIRouter()


def _resp(data, t0):
    return {"success": True, "data": data,
            "meta": {"timestamp": datetime.utcnow().isoformat() + "Z",
                     "processing_time_ms": round((time.time() - t0) * 1000),
                     "version": "1.0.0"}, "errors": []}


@router.post("/generate")
async def generate_signals(request: SignalRequest):
    t0 = time.time()
    try:
        md = MktData({})
        signals_out = []
        symbols = request.get_symbols()
        if not symbols:
            raise HTTPException(status_code=400, detail="Proporciona 'symbol' o 'symbols'")
        for symbol in symbols:
            try:
                bars = md.get_bars(symbol, period=request.period)
            except Exception as data_err:
                raise HTTPException(status_code=503,
                    detail=f"No se pudo obtener datos para {symbol}: {data_err}")
            hmm = HMMEngine({"n_candidates": [3, 4], "n_init": 3,
                              "min_train_bars": 252, "refit_interval": 5,
                              "zscore_window": 126})
            hmm.fit(bars)
            orchestrator = RegimeOrchestrator({"min_confidence": 0.55})
            orchestrator.setup_strategies(hmm.get_regime_info())
            state = hmm.predict_regime(bars)
            signal = orchestrator.generate_signal(symbol, bars, state)
            if signal:
                signals_out.append(signal.to_dict())
        return _resp({"signals": signals_out}, t0)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
