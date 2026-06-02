import streamlit as st
import requests
import plotly.graph_objects as go

API_BASE = "http://localhost:8000"

REGIME_COLORS = {
    "CRASH": "#FF4444",
    "BEAR": "#FF8C00",
    "NEUTRAL": "#888888",
    "BULL": "#00CC44",
    "EUPHORIA": "#9B59B6",
}

st.set_page_config(page_title="FUZION — Régimen de Mercado", layout="wide")
st.title("FUZION — Régimen de Mercado")

with st.sidebar:
    symbol = st.text_input("Símbolo", value="SPY")
    analyze_btn = st.button("Analizar")

if analyze_btn:
    try:
        resp = requests.post(
            f"{API_BASE}/api/regime/analyze",
            json={"symbol": symbol, "period": "2y"},
            timeout=30,
        )
        if resp.status_code == 503:
            st.warning("Datos de mercado no disponibles — conecta a internet con credenciales reales")
        else:
            resp.raise_for_status()
            data = resp.json()
            st.session_state["regime_data"] = data
    except requests.exceptions.ConnectionError:
        st.warning("Datos de mercado no disponibles — conecta a internet con credenciales reales")
    except Exception as e:
        st.error(f"Error: {e}")

if "regime_data" in st.session_state:
    data = st.session_state["regime_data"]
    regime = data.get("regime", "NEUTRAL")
    color = REGIME_COLORS.get(regime, "#888888")
    st.markdown(
        f'<div style="background-color:{color};padding:20px;border-radius:10px;text-align:center;">'
        f'<h1 style="color:white;margin:0;">{regime}</h1></div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    col1.metric("Probabilidad", f"{data.get('probability', 0) * 100:.1f}%")
    col2.metric("Retorno Esperado", f"{data.get('expected_return', 0) * 100:.2f}%")
    col3.metric("Volatilidad Esperada", f"{data.get('expected_volatility', 0) * 100:.2f}%")

    all_probs = data.get("all_probabilities", [])
    if all_probs:
        fig = go.Figure(
            go.Bar(
                x=[f"Régimen {i}" for i in range(len(all_probs))],
                y=[p * 100 for p in all_probs],
            )
        )
        fig.update_layout(title="Probabilidades por Régimen", yaxis_title="Probabilidad (%)")
        st.plotly_chart(fig, use_container_width=True)

    st.info(
        f"**Descripción:** {data.get('description', '')}\n\n"
        f"**Tamaño de posición:** {data.get('position_size_pct', 0)}%  "
        f"**Apalancamiento:** {data.get('leverage', 1)}x"
    )

    if data.get("is_flickering"):
        st.warning("Advertencia: El régimen está fluctuando (flickering)")
    if data.get("is_uncertain"):
        st.warning("Advertencia: El régimen es incierto")
