from fastapi import APIRouter, HTTPException
from datetime import datetime
import time
from typing import Optional
from api.models.regime_models import GreeksRequest, ScreenRequest, WheelScanRequest, CondorScanRequest, SpreadScanRequest, EarningsScanRequest
from options.common.chain_fetcher import OptionsChainFetcher
from options.common.greeks_calculator import GreeksCalculator
from options.common.iv_analyzer import IVAnalyzer
from options.common.options_screener import OptionsScreener, ScreenCriteria

router = APIRouter()
_fetcher = OptionsChainFetcher()
_greeks = GreeksCalculator()
_iv = IVAnalyzer(_fetcher)
_screener = OptionsScreener(_fetcher, _iv)


def _resp(data, t0):
    return {"success": True, "data": data,
            "meta": {"timestamp": datetime.utcnow().isoformat() + "Z",
                     "processing_time_ms": round((time.time() - t0) * 1000),
                     "version": "1.0.0"}, "errors": []}


@router.get("/chain/{symbol}")
async def get_options_chain(symbol: str, expiration: Optional[str] = None):
    t0 = time.time()
    try:
        chain = _fetcher.get_chain(symbol, expiration)
        return _resp({
            "symbol": chain.symbol,
            "expiration": chain.expiration,
            "dte": chain.dte,
            "underlying_price": chain.underlying_price,
            "calls_count": len(chain.calls),
            "puts_count": len(chain.puts),
            "calls": [vars(c) for c in chain.calls[:20]],
            "puts": [vars(p) for p in chain.puts[:20]],
        }, t0)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/greeks")
async def calculate_greeks(request: GreeksRequest):
    t0 = time.time()
    try:
        S, K, T = request.resolved_S(), request.resolved_K(), request.resolved_T()
        r, sigma = request.resolved_r(), request.resolved_sigma()
        g = _greeks.calculate_all_greeks(S, K, T, r, sigma, request.option_type)
        iv = _greeks.calculate_iv(
            _greeks._bs_price(S, K, T, r, sigma, request.option_type),
            S, K, T, r, request.option_type)
        return _resp({"delta": g.delta, "gamma": g.gamma, "theta": g.theta,
                      "vega": g.vega, "rho": g.rho, "iv": iv}, t0)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/iv/{symbol}")
async def get_iv_analysis(symbol: str):
    t0 = time.time()
    try:
        ivr = _iv.iv_rank(symbol)
        ivp = _iv.iv_percentile(symbol)
        iv_hv = _iv.iv_vs_hv(symbol)
        chain = _fetcher.get_chain(symbol)
        skew = _iv.iv_skew(chain)
        return _resp({
            "symbol": symbol,
            "iv_rank": ivr,
            "iv_percentile": ivp,
            "current_iv": iv_hv.current_iv,
            "hv20": iv_hv.hv20,
            "hv50": iv_hv.hv50,
            "iv_premium": iv_hv.iv_premium,
            "skew": {"put_skew": skew.put_skew, "call_skew": skew.call_skew,
                     "ratio": skew.skew_ratio},
        }, t0)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/screen")
async def screen_options(request: ScreenRequest):
    t0 = time.time()
    try:
        criteria = ScreenCriteria(
            min_iv_rank=request.min_iv_rank,
            max_iv_rank=request.max_iv_rank,
            min_dte=request.min_dte,
            max_dte=request.max_dte,
        )
        results = _screener.scan_universe(request.universe, criteria)
        return _resp({"results": [vars(r) for r in results]}, t0)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wheel/scan")
async def scan_wheel(request: WheelScanRequest):
    t0 = time.time()
    try:
        from options.wheel.wheel_engine import WheelEngine
        engine = WheelEngine(_fetcher, _iv)
        candidates = engine.scan_csp_candidates(
            request.universe, request.account_size, request.regime)
        return _resp({"candidates": [vars(c) for c in candidates[:10]]}, t0)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/condor/scan")
async def scan_condors(request: CondorScanRequest):
    t0 = time.time()
    try:
        from options.iron_condor.condor_engine import IronCondorEngine
        engine = IronCondorEngine(_fetcher, _iv)
        candidates = engine.find_condors(
            request.symbol, request.account_size, request.regime)
        return _resp({"candidates": [vars(c) for c in candidates[:5]]}, t0)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/spread/scan")
async def scan_spreads(request: SpreadScanRequest):
    t0 = time.time()
    try:
        from options.credit_spread.spread_engine import CreditSpreadEngine
        engine = CreditSpreadEngine(_fetcher, _iv)
        candidates = engine.find_spreads(
            request.symbol, request.direction, request.account_size, request.regime)
        return _resp({"candidates": [vars(c) for c in candidates[:5]]}, t0)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/earnings/scan")
async def scan_earnings(request: EarningsScanRequest):
    t0 = time.time()
    try:
        from options.earnings.earnings_engine import EarningsEngine
        engine = EarningsEngine(_fetcher, _iv)
        plays = engine.find_earnings_plays(request.universe, request.regime)
        return _resp({"plays": [vars(p) for p in plays[:10]]}, t0)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
