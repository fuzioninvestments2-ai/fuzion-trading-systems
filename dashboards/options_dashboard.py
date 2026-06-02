import streamlit as st
import requests
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="FUZION — Dashboard de Opciones", layout="wide")
st.title("FUZION — Dashboard de Opciones")

tab_greeks, tab_iv, tab_screener = st.tabs(["Greeks Calculator", "IV Analysis", "Screener"])

with tab_greeks:
    col1, col2 = st.columns(2)
    with col1:
        spot = st.number_input("Spot", value=450.0, step=1.0)
        strike = st.number_input("Strike", value=450.0, step=1.0)
        expiry_days = st.slider("Días al vencimiento", min_value=1, max_value=365, value=30)
    with col2:
        sigma = st.slider("Volatilidad implícita (σ)", min_value=0.05, max_value=2.0, step=0.01, value=0.20)
        option_type = st.selectbox("Tipo", ["call", "put"])

    calc_btn = st.button("Calcular Greeks")

    if calc_btn:
        try:
            resp = requests.post(
                f"{API_BASE}/api/options/greeks",
                json={
                    "spot": spot,
                    "strike": strike,
                    "expiry_days": expiry_days,
                    "sigma": sigma,
                    "option_type": option_type,
                },
                timeout=15,
            )
            resp.raise_for_status()
            st.session_state["greeks_data"] = resp.json()
        except Exception as e:
            st.error(f"Error calculando Greeks: {e}")

    if "greeks_data" in st.session_state:
        g = st.session_state["greeks_data"]
        gc1, gc2, gc3, gc4, gc5 = st.columns(5)
        gc1.metric("Delta", f"{g.get('delta', 0):.4f}")
        gc2.metric("Gamma", f"{g.get('gamma', 0):.4f}")
        gc3.metric("Theta", f"{g.get('theta', 0):.4f}")
        gc4.metric("Vega", f"{g.get('vega', 0):.4f}")
        gc5.metric("Rho", f"{g.get('rho', 0):.4f}")

    spot_range = np.linspace(spot * 0.8, spot * 1.2, 50)
    T = expiry_days / 365.0
    r = 0.05

    def bs_delta(S, K, T, sigma, r, option_type):
        if T <= 0:
            return 0.0
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        if option_type == "call":
            return norm.cdf(d1)
        return norm.cdf(d1) - 1

    deltas = [bs_delta(s, strike, T, sigma, r, option_type) for s in spot_range]
    fig_delta = go.Figure(go.Scatter(x=spot_range, y=deltas, mode="lines"))
    fig_delta.update_layout(title="Delta vs Spot", xaxis_title="Spot", yaxis_title="Delta")
    st.plotly_chart(fig_delta, use_container_width=True)

with tab_iv:
    iv_symbol = st.text_input("Símbolo", value="SPY", key="iv_symbol")
    iv_btn = st.button("Analizar IV")

    if iv_btn:
        try:
            resp = requests.get(f"{API_BASE}/api/options/iv/{iv_symbol}", timeout=15)
            if resp.status_code == 503:
                st.warning("Datos de mercado no disponibles — conecta a internet con credenciales reales")
            else:
                resp.raise_for_status()
                st.session_state["iv_data"] = resp.json()
        except requests.exceptions.ConnectionError:
            st.warning("Datos de mercado no disponibles — conecta a internet con credenciales reales")
        except Exception as e:
            st.error(f"Error: {e}")

    if "iv_data" in st.session_state:
        iv = st.session_state["iv_data"]
        ivc1, ivc2 = st.columns(2)
        ivc1.metric("IV Rank", f"{iv.get('iv_rank', 0):.1f}")
        ivc2.metric("IV Percentile", f"{iv.get('iv_percentile', 0):.1f}")

        current_iv = iv.get("current_iv", 0)
        hv20 = iv.get("hv20", 0)
        hv50 = iv.get("hv50", 0)
        fig_iv = go.Figure(
            go.Bar(x=["IV Actual", "HV20", "HV50"], y=[current_iv * 100, hv20 * 100, hv50 * 100])
        )
        fig_iv.update_layout(title="IV vs HV", yaxis_title="Volatilidad (%)")
        st.plotly_chart(fig_iv, use_container_width=True)

        skew = iv.get("skew", {})
        if skew:
            st.subheader("Skew")
            st.json(skew)

with tab_screener:
    universe = st.multiselect(
        "Universo de símbolos",
        options=["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "TSLA", "META"],
        default=["SPY", "QQQ", "AAPL", "MSFT", "NVDA"],
    )
    sc1, sc2 = st.columns(2)
    with sc1:
        min_iv_rank = st.slider("Min IV Rank", min_value=0, max_value=100, value=0)
        min_dte = st.slider("Min DTE", min_value=0, max_value=365, value=7)
    with sc2:
        max_iv_rank = st.slider("Max IV Rank", min_value=0, max_value=100, value=100)
        max_dte = st.slider("Max DTE", min_value=0, max_value=365, value=60)

    scan_btn = st.button("Scan Universe")

    if scan_btn:
        try:
            resp = requests.post(
                f"{API_BASE}/api/options/screen",
                json={
                    "universe": universe,
                    "min_iv_rank": min_iv_rank,
                    "max_iv_rank": max_iv_rank,
                    "min_dte": min_dte,
                    "max_dte": max_dte,
                },
                timeout=60,
            )
            if resp.status_code == 503:
                st.warning("Datos de mercado no disponibles — conecta a internet con credenciales reales")
            else:
                resp.raise_for_status()
                st.session_state["screener_data"] = resp.json()
        except requests.exceptions.ConnectionError:
            st.warning("Datos de mercado no disponibles — conecta a internet con credenciales reales")
        except Exception as e:
            st.error(f"Error: {e}")

    if "screener_data" in st.session_state:
        import pandas as pd
        results = st.session_state["screener_data"]
        if isinstance(results, list):
            st.dataframe(pd.DataFrame(results))
        else:
            st.dataframe(pd.DataFrame([results]))
