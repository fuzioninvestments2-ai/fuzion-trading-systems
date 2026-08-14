"""
core/indicator_set.py (fuzion_fx)
=================================
LOS 8 INDICADORES VOTANTES del motor cuantico (estrategia de Alex, doc fuente).
Cada indicador vota con DIRECCION (+1 CALL / -1 PUT / 0 neutro) y FUERZA (0..1:
que tan clara es la senal). El motor cuantico (core/quantum_engine.py) los combina
ponderando por el modo (Slide/Oscillate del ADX) y por temporalidad.

PORQUE dir+fuerza y no solo un voto: dos indicadores pueden decir "CALL" pero uno
al borde (fuerza 0.1) y otro rotundo (fuerza 0.9). Tratarlos igual pierde la
informacion que un trader SI usa. La fuerza es lo que pondera el motor.

Entrada: velas en formato del sistema
  {"open":[...],"high":[...],"low":[...],"close":[...],"volume":[...]} (listas
  cronologicas, viejo -> nuevo). Determinista, SIN red, sin pandas (solo numpy).
"""

from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np

CALL = 1
PUT = -1
NEUTRAL = 0

MIN_VELAS = 60          # sin esta cantidad, los indicadores largos no maduran


# ----------------------------------------------------------------- helpers math
def _arr(x: Sequence[float]) -> np.ndarray:
    return np.asarray(x, dtype=float)


def _ema(x: np.ndarray, span: int) -> np.ndarray:
    """EMA (mismo largo que x). alfa = 2/(span+1)."""
    a = 2.0 / (span + 1.0)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def _rsi(close: np.ndarray, n: int = 14) -> np.ndarray:
    d = np.diff(close, prepend=close[0])
    up = np.where(d > 0, d, 0.0)
    dn = np.where(d < 0, -d, 0.0)
    au = _ema(up, n); ad = _ema(dn, n)
    rs = au / np.where(ad == 0, 1e-12, ad)
    return 100.0 - 100.0 / (1.0 + rs)


def _macd(close: np.ndarray, f: int = 12, s: int = 26, sig: int = 9):
    macd = _ema(close, f) - _ema(close, s)
    signal = _ema(macd, sig)
    return macd, signal, macd - signal          # macd, signal, histograma


def _sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.empty_like(x)
    for i in range(len(x)):
        lo = max(0, i - n + 1)
        out[i] = x[lo:i + 1].mean()
    return out


def _std(x: np.ndarray, n: int) -> np.ndarray:
    out = np.empty_like(x)
    for i in range(len(x)):
        lo = max(0, i - n + 1)
        out[i] = x[lo:i + 1].std()
    return out


def _atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    prev_c = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    return _ema(tr, n)


def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def _voto(direccion: int, fuerza: float) -> Dict[str, float]:
    """Voto normalizado. Si la fuerza es ~0, la direccion se vuelve NEUTRAL (una
    senal sin fuerza no arrastra al motor)."""
    f = _clip01(fuerza)
    if f < 1e-3:
        return {"dir": NEUTRAL, "fuerza": 0.0}
    return {"dir": int(direccion), "fuerza": f}


# ----------------------------------------------------------------- indicadores
def ind_rsi(o, h, l, c, v) -> Dict[str, float]:
    """Reversion. RSI<50 sesga CALL (sobreventa -> rebote), >50 sesga PUT. La
    FUERZA crece con la distancia a 50 (RSI 20 -> ~0.9; RSI 45 -> ~0.15)."""
    r = float(_rsi(c)[-1])
    direccion = CALL if r < 50 else PUT
    fuerza = abs(50.0 - r) / 33.33          # 30/33.33=0.9 ; 5/33.33=0.15
    return _voto(direccion, fuerza)


def ind_macd(o, h, l, c, v) -> Dict[str, float]:
    """Tendencia/momentum. Direccion = signo del histograma (MACD vs senal). La
    FUERZA sube con la magnitud del histograma vs su volatilidad reciente y si el
    histograma CRECE en la direccion (momentum que acelera)."""
    _, _, hist = _macd(c)
    hh = float(hist[-1])
    direccion = CALL if hh > 0 else (PUT if hh < 0 else NEUTRAL)
    escala = float(np.abs(hist[-20:]).mean()) + 1e-12
    magnitud = abs(hh) / (3.0 * escala)
    pendiente = hh - float(hist[-2])
    acelera = 1.0 if pendiente * direccion > 0 else 0.55
    return _voto(direccion, magnitud * acelera)


def ind_bollinger(o, h, l, c, v) -> Dict[str, float]:
    """Reversion/volatilidad. Precio cerca de la banda inferior -> CALL (rebote),
    cerca de la superior -> PUT. FUERZA = distancia relativa al centro. Si las
    bandas estan comprimidas (squeeze) se reduce (mejor esperar breakout)."""
    mid = _sma(c, 20); sd = _std(c, 20)
    ancho = 4.0 * float(sd[-1])                       # 2 desv a cada lado
    if ancho < 1e-12:
        return _voto(NEUTRAL, 0.0)
    pos = (float(c[-1]) - float(mid[-1])) / (0.5 * ancho)   # -1 abajo, +1 arriba
    direccion = CALL if pos < 0 else PUT
    fuerza = abs(pos)
    # squeeze: ancho chico respecto al precio -> reversion menos fiable.
    if ancho / float(c[-1]) < 0.001:
        fuerza *= 0.5
    return _voto(direccion, fuerza)


def ind_ema(o, h, l, c, v) -> Dict[str, float]:
    """Tendencia. Apilamiento EMA 9>21>55 (alcista) o 9<21<55 (bajista). Direccion
    por 9 vs 55; FUERZA por separacion entre EMAs + pendiente. Apilamiento perfecto
    da fuerza plena; parcial, la mitad."""
    e9 = _ema(c, 9); e21 = _ema(c, 21); e55 = _ema(c, 55)
    px = float(c[-1])
    up = e9[-1] > e21[-1] > e55[-1]
    dn = e9[-1] < e21[-1] < e55[-1]
    direccion = CALL if e9[-1] >= e55[-1] else PUT
    sep = abs(float(e9[-1]) - float(e55[-1])) / px          # separacion relativa
    pend = abs(float(e9[-1]) - float(e9[-4])) / px          # pendiente reciente
    base = sep * 220.0 + pend * 320.0                       # escala para FX
    fuerza = base if (up or dn) else base * 0.5
    return _voto(direccion, fuerza)


def ind_estocastico(o, h, l, c, v) -> Dict[str, float]:
    """Reversion/momentum. %K y %D (14,3,3). %K bajo (<50) sesga CALL, alto PUT.
    Un CRUCE de %K sobre %D en la direccion refuerza la fuerza."""
    n = 14
    hh = _arr([max(h[max(0, i - n + 1):i + 1]) for i in range(len(c))])
    ll = _arr([min(l[max(0, i - n + 1):i + 1]) for i in range(len(c))])
    rango = np.where(hh - ll == 0, 1e-12, hh - ll)
    k_raw = 100.0 * (c - ll) / rango
    k = _sma(k_raw, 3); d = _sma(k, 3)
    kk = float(k[-1])
    direccion = CALL if kk < 50 else PUT
    extrem = (50.0 - kk) / 50.0 if direccion == CALL else (kk - 50.0) / 50.0
    cruce_up = k[-2] < d[-2] and k[-1] >= d[-1]
    cruce_dn = k[-2] > d[-2] and k[-1] <= d[-1]
    refuerzo = 1.0 if ((cruce_up and direccion == CALL) or
                       (cruce_dn and direccion == PUT)) else 0.6
    return _voto(direccion, extrem * refuerzo * 1.4)


def ind_donchian(o, h, l, c, v) -> Dict[str, float]:
    """Tendencia/breakout (20). Cierre que rompe el maximo del canal previo -> CALL;
    que rompe el minimo -> PUT. FUERZA = cuanto pasa el borde, en ATR."""
    n = 20
    if len(c) < n + 2:
        return _voto(NEUTRAL, 0.0)
    canal_up = max(h[-n - 1:-1])                    # canal SIN la vela actual
    canal_lo = min(l[-n - 1:-1])
    px = float(c[-1])
    atr = float(_atr(_arr(h), _arr(l), _arr(c))[-1]) + 1e-12
    if px >= canal_up:
        return _voto(CALL, (px - canal_up) / atr + 0.2)
    if px <= canal_lo:
        return _voto(PUT, (canal_lo - px) / atr + 0.2)
    return _voto(NEUTRAL, 0.0)                       # dentro del canal: sin breakout


def ind_vwap(o, h, l, c, v) -> Dict[str, float]:
    """Nivel clave. Precio por encima del VWAP -> sesgo CALL (soporte), por debajo
    -> PUT (resistencia). Si no hay volumen real (FX de PO suele mandar 0) se usa
    el precio tipico sin ponderar (VWAP -> promedio movil de tipicos)."""
    tp = (_arr(h) + _arr(l) + _arr(c)) / 3.0
    vol = _arr(v)
    if float(vol.sum()) <= 0:
        vwap = _sma(tp, 20)                          # sin volumen: media de tipicos
    else:
        cv = np.cumsum(vol); ctpv = np.cumsum(tp * vol)
        vwap = ctpv / np.where(cv == 0, 1e-12, cv)
    px = float(c[-1]); vw = float(vwap[-1])
    direccion = CALL if px > vw else PUT
    fuerza = abs(px - vw) / px * 350.0
    return _voto(direccion, fuerza)


def ind_momentum_volumen(o, h, l, c, v) -> Dict[str, float]:
    """CONFIRMACION (no vota solo; el motor lo usa como MULTIPLICADOR de fuerza).
    Direccion = signo del momentum (precio ahora vs hace 4 velas). La fuerza sube
    si el volumen acompana; sin volumen real, solo el momentum."""
    if len(c) < 5:
        return _voto(NEUTRAL, 0.0)
    mom = float(c[-1]) - float(c[-4])
    direccion = CALL if mom > 0 else (PUT if mom < 0 else NEUTRAL)
    base = abs(mom) / float(c[-1]) * 300.0
    vol = _arr(v)
    if float(vol.sum()) > 0:
        vol_sube = float(vol[-1]) > float(vol[-5:].mean())
        base *= 1.2 if vol_sube else 0.8
    voto = _voto(direccion, base)
    voto["es_multiplicador"] = True
    return voto


# nombre -> (funcion, tipo). tipo: 'tendencia' | 'reversion' | 'nivel' | 'mult'
INDICADORES = {
    "rsi": (ind_rsi, "reversion"),
    "macd": (ind_macd, "tendencia"),
    "bollinger": (ind_bollinger, "reversion"),
    "ema": (ind_ema, "tendencia"),
    "estocastico": (ind_estocastico, "reversion"),
    "donchian": (ind_donchian, "tendencia"),
    "vwap": (ind_vwap, "nivel"),
    "momentum": (ind_momentum_volumen, "mult"),
}


def votar(candles: Dict[str, Sequence[float]]) -> Dict[str, Dict]:
    """
    Corre los 8 indicadores sobre las velas y devuelve, por nombre, su voto:
      {nombre: {"dir": +1/-1/0, "fuerza": 0..1, "tipo": ...}}.
    Si faltan velas (< MIN_VELAS) devuelve {} (el motor no opera sin datos).
    'volume' es opcional (default 0 -> VWAP/momentum caen a modo sin-volumen).
    """
    c = candles.get("close", [])
    if c is None or len(c) < MIN_VELAS:
        return {}
    o = candles.get("open", c); h = candles.get("high", c)
    l = candles.get("low", c); v = candles.get("volume", [0.0] * len(c))
    o = _arr(o); h = _arr(h); l = _arr(l); c = _arr(c); v = _arr(v)
    out: Dict[str, Dict] = {}
    for nombre, (fn, tipo) in INDICADORES.items():
        try:
            voto = fn(o, h, l, c, v)
        except Exception:
            voto = {"dir": NEUTRAL, "fuerza": 0.0}
        voto["tipo"] = tipo
        out[nombre] = voto
    return out
