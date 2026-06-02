import streamlit as st
import requests
import plotly.graph_objects as go
import pandas as pd
from datetime import date

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="FUZION — Backtest Walk-Forward", layout="wide")
st.title("FUZION — Backtest Walk-Forward")

with st.sidebar:
    symbol = st.text_input("Símbolo", value="SPY")
    start_date = st.date_input("Fecha inicio", value=date(2020, 1, 1))
    end_date = st.date_input("Fecha fin", value=date(2024, 12, 31))
    initial_equity = st.number_input("Capital inicial", value=100000, step=1000)
    run_btn = st.button("Ejecutar Backtest")

if run_btn:
    try:
        resp = requests.post(
            f"{API_BASE}/api/backtest/run",
            json={
                "symbol": symbol,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "initial_equity": initial_equity,
            },
            timeout=120,
        )
        if resp.status_code == 503:
            st.warning("Datos de mercado no disponibles — conecta a internet con credenciales reales")
        else:
            resp.raise_for_status()
            st.session_state["backtest_data"] = resp.json()
    except requests.exceptions.ConnectionError:
        st.warning("Datos de mercado no disponibles — conecta a internet con credenciales reales")
    except Exception as e:
        st.error(f"Error: {e}")

if "backtest_data" in st.session_state:
    data = st.session_state["backtest_data"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Return", f"{data.get('total_return', 0) * 100:.2f}%")
    col2.metric("CAGR", f"{data.get('cagr', 0) * 100:.2f}%")
    col3.metric("Sharpe Ratio", f"{data.get('sharpe_ratio', 0):.2f}")

    col4, col5, col6 = st.columns(3)
    col4.metric("Max Drawdown", f"{data.get('max_drawdown', 0) * 100:.2f}%")
    col5.metric("Win Rate", f"{data.get('win_rate', 0) * 100:.2f}%")
    col6.metric("Profit Factor", f"{data.get('profit_factor', 0):.2f}")

    equity_curve = data.get("equity_curve", {})
    if equity_curve:
        eq_df = pd.Series(equity_curve)
        fig_eq = go.Figure(go.Scatter(x=eq_df.index, y=eq_df.values, mode="lines"))
        fig_eq.update_layout(title="Curva de Equity", xaxis_title="Fecha", yaxis_title="Equity ($)")
        st.plotly_chart(fig_eq, use_container_width=True)

    trades = data.get("trades", [])
    if trades:
        trades_df = pd.DataFrame(trades)
        st.subheader("Últimas 20 operaciones")
        st.dataframe(trades_df.tail(20))

    regime_breakdown = data.get("regime_breakdown", {})
    if regime_breakdown:
        fig_rb = go.Figure(
            go.Bar(x=list(regime_breakdown.keys()), y=list(regime_breakdown.values()))
        )
        fig_rb.update_layout(title="Rendimiento por Régimen")
        st.plotly_chart(fig_rb, use_container_width=True)

    benchmarks = data.get("benchmarks", {})
    if benchmarks:
        fig_bm = go.Figure(
            go.Bar(x=list(benchmarks.keys()), y=[v * 100 for v in benchmarks.values()])
        )
        fig_bm.update_layout(title="Comparación con Benchmarks", yaxis_title="Retorno (%)")
        st.plotly_chart(fig_bm, use_container_width=True)
