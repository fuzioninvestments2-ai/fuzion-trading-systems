from fastapi import APIRouter, HTTPException
from datetime import datetime
import time
from api.models.regime_models import RegimeAnalysisRequest
from core.hmm_engine import HMMEngine
from data.market_data import MarketData as MktData

router = APIRouter()
_hmm_cache = {}


def _get_hmm(config: dict) -> HMMEngine:
    return HMMEngine(config)


def _make_response(data: dict, t0: float) -> dict:
    return {
        "success": True,
        "data": data,
        "meta": {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "processing_time_ms": round((time.time() - t0) * 1000),
            "version": "1.0.0",
        },
        "errors": [],
    }


@router.post("/analyze")
async def analyze_regime(request: RegimeAnalysisRequest):
    t0 = time.time()
    try:
        md = MktData({})
        try:
            bars = md.get_bars(request.symbol, period=request.period)
        except Exception as data_err:
            raise HTTPException(status_code=503,
                detail=f"No se pudo obtener datos para {request.symbol}: {data_err}")
        hmm = HMMEngine({
            "n_candidates": [3, 4, 5], "n_init": 5, "min_train_bars": 252,
            "refit_interval": 5, "zscore_window": 126,
        })
        hmm.fit(bars)
        state = hmm.predict_regime(bars)
        regime = state.current_regime
        return _make_response({
            "symbol": request.symbol,
            "regime": regime.label.value,
            "probability": round(state.regime_probability, 4),
            "is_uncertain": state.is_uncertain,
            "is_flickering": state.is_flickering,
            "bars_in_regime": state.bars_in_regime,
            "expected_return": round(regime.expected_return, 4),
            "expected_volatility": round(regime.expected_volatility, 4),
            "position_size_pct": round(regime.position_size_pct, 4),
            "leverage": regime.leverage,
            "description": regime.description,
            "all_probabilities": state.all_probabilities.tolist(),
        }, t0)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/current/{symbol}")
async def get_current_regime(symbol: str):
    t0 = time.time()
    try:
        md = MktData({})
        try:
            bars = md.get_bars(symbol, period="2y")
        except Exception as data_err:
            raise HTTPException(status_code=503,
                detail=f"No se pudo obtener datos para {symbol}: {data_err}")
        hmm = HMMEngine({"n_candidates": [3, 4], "n_init": 3, "min_train_bars": 252})
        hmm.fit(bars)
        state = hmm.predict_regime(bars)
        return _make_response({
            "symbol": symbol,
            "regime": state.current_regime.label.value,
            "probability": round(state.regime_probability, 4),
        }, t0)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
