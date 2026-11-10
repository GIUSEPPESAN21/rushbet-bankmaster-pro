"""AI Analyst: informe con Gemini o diagnóstico local determinista."""

from __future__ import annotations

import os

import streamlit as st

from core.ai_analyst import DEFAULT_MODEL, generate_analysis_report
from ui import components as ui
from ui.state import load

PRESETS = {
    "Diagnóstico general": "Analiza la composición del riesgo, destaca oportunidades de mejora y recomienda un plan de staking para la próxima sesión.",
    "¿Qué mercados pausar?": "Identifica los deportes, mercados y rangos de cuota con peor rendimiento y dime cuáles pausar y por qué.",
    "Plan para llegar a breakeven": "Propón un plan realista, con número de apuestas y tamaño de unidad, para alcanzar la meta de breakeven sin superar el riesgo máximo.",
    "Disciplina y sesgos": "Revisa si hay señales de tilt, sobreapuesta tras pérdidas o stakes fuera del plan.",
}


def _secret(name: str):
    value = os.getenv(name)
    if value:
        return value
    try:
        return st.secrets.get(name)
    except Exception:  # sin secrets.toml
        return None


def render() -> None:
    bets, cfg = load()
    api_key = _secret("GEMINI_API_KEY")
    model = _secret("GEMINI_MODEL") or DEFAULT_MODEL
    ui.page_header("AI Analyst", "Informe ejecutivo de tu bank con recomendaciones accionables.", "auto_awesome",
                   badges=[{"text": f"Gemini · {model}" if api_key else "Modo local", "tone": "success" if api_key else "neutral",
                            "icon": "cloud_done" if api_key else "computer"}])

    preset = st.pills("Plantillas", list(PRESETS), default="Diagnóstico general", key="ai_preset")
    prompt = st.text_area("Solicitud para la IA", value=PRESETS.get(preset or "", ""), height=110, key=f"ai_prompt_{preset}")

    if st.button("Generar análisis", type="primary", icon=":material/auto_awesome:"):
        with st.spinner("Analizando tu historial…"):
            st.session_state["ai_result"] = generate_analysis_report(bets, cfg, prompt, api_key=api_key, model=model)

    result = st.session_state.get("ai_result")
    if result:
        with st.container(border=True):
            ui.section_title("Informe generado", "description",
                             ("Generado por Gemini" if result.source == "gemini" else "Diagnóstico local") +
                             (f" · {result.note}" if result.note else ""))
            st.markdown(result.text)
    elif not api_key:
        st.info("Configura `GEMINI_API_KEY` (variable de entorno, `.env` o Secrets de Streamlit) para usar Gemini. "
                "Sin clave se genera un diagnóstico local con tus métricas.", icon=":material/key:")
    st.caption("La IA es apoyo de análisis: no garantiza resultados ni sustituye tu criterio.")
