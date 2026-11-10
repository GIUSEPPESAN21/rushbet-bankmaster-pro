"""Rushbet BankMaster Pro · punto de entrada de Streamlit.

Ejecutar con:  streamlit run app.py
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from core import database as db
from core.analytics import summarize_bets
from ui import components as ui
from ui.views import ai, analytics, dashboard, history, new_bet, settings

ASSETS = Path(__file__).resolve().parent / "assets"

st.set_page_config(page_title="Rushbet BankMaster Pro", page_icon=str(ASSETS / "icon.svg"), layout="wide",
                   initial_sidebar_state="expanded")


@st.cache_resource(show_spinner=False)
def _init_db_once() -> bool:
    db.init_db()
    return True


def _sidebar() -> None:
    bets, cfg = db.get_bets(), db.load_settings()
    m = summarize_bets(bets, cfg)
    with st.sidebar:
        ui.sidebar_bank_card(m["current_bankroll"], m["net_profit"], m["breakeven_progress"], cfg.currency)
        st.caption("Apuesta con responsabilidad. Línea de ayuda: consulta el programa de juego responsable de tu operador.")


def main() -> None:
    _init_db_once()
    ui.load_theme()
    st.logo(str(ASSETS / "logo.svg"), size="large", icon_image=str(ASSETS / "icon.svg"))

    pages = {
        "Operación": [
            st.Page(dashboard.render, title="Dashboard", icon=":material/space_dashboard:", url_path="dashboard", default=True),
            st.Page(new_bet.render, title="Nueva apuesta", icon=":material/add_circle:", url_path="nueva"),
            st.Page(history.render, title="Historial", icon=":material/receipt_long:", url_path="historial"),
        ],
        "Inteligencia": [
            st.Page(analytics.render, title="Analítica", icon=":material/insights:", url_path="analitica"),
            st.Page(ai.render, title="AI Analyst", icon=":material/auto_awesome:", url_path="ai"),
        ],
        "Sistema": [
            st.Page(settings.render, title="Configuración", icon=":material/settings:", url_path="configuracion"),
        ],
    }
    page = st.navigation(pages)
    _sidebar()
    page.run()


if __name__ == "__main__":
    main()
