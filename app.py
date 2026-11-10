from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from ai_analyst import generate_analysis_report
from analytics import BASE_BANKROLL, BREAKEVEN_TARGET, SUBSCRIPTION_COST, build_cumulative_bankroll, get_stake_profile, summarize_bets
from database import (
    add_bet,
    delete_bet,
    get_bets,
    get_setting,
    init_db,
    save_setting,
    update_bet,
)

st.set_page_config(page_title="Rushbet BankMaster Pro", layout="wide")


def safe_bankroll() -> float:
    return float(get_setting("base_bankroll", BASE_BANKROLL))


def render_dashboard() -> None:
    st.title("Dashboard Ejecutivo")
    bankroll = safe_bankroll()
    bets = get_bets()
    metrics = summarize_bets(bets, bankroll)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Bankroll operativo", f"${bankroll:,.0f} COP")
    c2.metric("Net Profit", f"${metrics['net_profit']:,.0f} COP")
    c3.metric("ROI", f"{metrics['roi']:.2f}%")
    c4.metric("Win Rate", f"{metrics['win_rate']:.2f}%")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Yield", f"{metrics['yield']:.2f}%")
    c6.metric("Breakeven net", f"${BREAKEVEN_TARGET:,.0f} COP")
    c7.metric("Meta de objetivo", f"${metrics['breakeven_gap']:,.0f} COP")
    c8.metric("Kelly ref.", f"{metrics['kelly_reference']:.2f}")

    stake_table = pd.DataFrame.from_dict(get_stake_profile(bankroll), orient="index").reset_index()
    stake_table = stake_table.rename(columns={"index": "Perfil", "confidence": "Confianza", "pct": "% del bank", "cash": "Stake COP"})
    stake_table["% del bank"] = stake_table["% del bank"].map(lambda x: f"{x * 100:.0f}%")
    stake_table["Stake COP"] = stake_table["Stake COP"].map(lambda x: f"${x:,.0f} COP")

    st.subheader("Estructura de stakes")
    st.dataframe(stake_table, use_container_width=True, hide_index=True)

    cumulative = build_cumulative_bankroll(bets, bankroll)
    cumulative_df = pd.DataFrame(cumulative)
    fig = px.line(cumulative_df, x="date", y="bankroll", markers=True, title="Evolución del bankroll")
    fig.update_layout(height=400, margin=dict(l=15, r=15, t=40, b=15))
    st.plotly_chart(fig, use_container_width=True)

    if bets:
        df = pd.DataFrame(bets)
        if "net_profit" in df.columns:
            df["net_profit"] = pd.to_numeric(df["net_profit"], errors="coerce")
        sport_profit = df.groupby("sport")["net_profit"].sum().sort_values(ascending=False)
        with st.container():
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("Ganancias por deporte")
                st.bar_chart(sport_profit)
            with col_b:
                st.subheader("Últimas apuestas")
                recent = df.sort_values("id", ascending=False).head(8)
                st.dataframe(recent[["bet_date", "sport", "selection", "odds", "stake", "status", "net_profit"]], use_container_width=True, hide_index=True)


def render_bet_log() -> None:
    st.title("Registro de Apuestas")
    bankroll = safe_bankroll()
    bets = get_bets()

    with st.form("bet_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            bet_date = st.date_input("Fecha", value=date.today())
            sport = st.text_input("Deporte", value="Fútbol")
            market = st.text_input("Mercado", value="1X2")
        with col2:
            event_name = st.text_input("Evento", value="Equipo A vs Equipo B")
            selection = st.text_input("Selección", value="Local")
            odds = st.number_input("Odds (decimal)", min_value=1.01, value=2.10, step=0.05)
        with col3:
            stake = st.number_input("Stake COP", min_value=1000.0, value=5000.0, step=1000.0)
            confidence = st.slider("Confianza (%)", 50, 99, 80)
            unit_type = st.selectbox("Tipo de stake", ["1U", "2U", "3U", "4U", "Whale"])

        status = st.selectbox("Estado", ["open", "won", "lost", "void"])
        result = st.selectbox("Resultado", ["pending", "won", "lost", "void"])
        notes = st.text_area("Notas", "")

        submitted = st.form_submit_button("Guardar apuesta")
        if submitted:
            add_bet(
                bet_date=bet_date.isoformat(),
                sport=sport,
                market=market,
                event_name=event_name,
                selection=selection,
                odds=float(odds),
                stake=float(stake),
                confidence=float(confidence),
                unit_type=unit_type,
                status=status,
                result=result,
                notes=notes,
            )
            st.success("Apuesta guardada exitosamente.")

    if bets:
        df = pd.DataFrame(bets)
        st.subheader("Historial actual")
        st.dataframe(df[["bet_date", "sport", "event_name", "selection", "odds", "stake", "status", "net_profit"]], use_container_width=True, hide_index=True)

        for bet in bets:
            with st.container():
                st.markdown(f"### {bet['event_name']} · {bet['selection']}")
                st.write(f"Deporte: {bet['sport']} | Mercado: {bet['market']} | Fecha: {bet['bet_date']} | Stake: ${bet['stake']:,.0f} COP | Net: ${bet['net_profit']:,.0f} COP")
                if st.button(f"Eliminar apuesta #{bet['id']}", key=f"delete_{bet['id']}"):
                    delete_bet(bet["id"])
                    st.rerun()
    else:
        st.info("Aún no hay apuestas registradas. Agrega la primera para iniciar la base analítica.")


def render_analytics() -> None:
    st.title("Analítica Financiera")
    bankroll = safe_bankroll()
    bets = get_bets()
    metrics = summarize_bets(bets, bankroll)
    df = pd.DataFrame(bets)
    if not df.empty:
        df["stake"] = pd.to_numeric(df["stake"], errors="coerce")
        df["net_profit"] = pd.to_numeric(df["net_profit"], errors="coerce")
        df["odds"] = pd.to_numeric(df["odds"], errors="coerce")

        profits_by_result = df.groupby("result")["net_profit"].sum().reset_index()
        fig_result = px.bar(profits_by_result, x="result", y="net_profit", title="Resultado por tipo")
        st.plotly_chart(fig_result, use_container_width=True)

    st.subheader("Métricas clave")
    metric_cols = st.columns(5)
    metric_cols[0].metric("Bankroll base", f"${BASE_BANKROLL:,.0f} COP")
    metric_cols[1].metric("Suscripción", f"-${SUBSCRIPTION_COST:,.0f} COP")
    metric_cols[2].metric("ROI", f"{metrics['roi']:.2f}%")
    metric_cols[3].metric("Yield", f"{metrics['yield']:.2f}%")
    metric_cols[4].metric("Kelly promedio", f"{metrics['kelly_reference']:.2f}")

    st.subheader("Plan de staking sugerido")
    profile = pd.DataFrame.from_dict(get_stake_profile(bankroll), orient="index").reset_index()
    profile.columns = ["Perfil", "Confianza", "% del bank", "Stake COP"]
    st.dataframe(profile, use_container_width=True, hide_index=True)

    if df.empty:
        st.info("Añade un conjunto mínimo de apuestas para activar el panel analítico completo.")


def render_ai() -> None:
    st.title("AI Analyst")
    bankroll = safe_bankroll()
    bets = get_bets()
    prompt = st.text_area(
        "Solicitud para la IA",
        value="Analiza la composición del riesgo, destaca oportunidades de mejora y recomienda un plan de staking para la próxima sesión.",
        height=120,
    )

    if st.button("Generar análisis con Gemini"):
        analysis = generate_analysis_report(bets, bankroll, prompt)
        st.markdown("### Informe generado")
        st.write(analysis)
    else:
        st.info("Configura la variable de entorno GEMINI_API_KEY para activar Gemini 3 Flash. Si no existe, se usa el análisis local seguro.")


def render_settings() -> None:
    st.title("Configuración del Bankroll")
    bankroll = float(get_setting("base_bankroll", BASE_BANKROLL))
    subscription = float(get_setting("subscription_cost", SUBSCRIPTION_COST))
    breakeven = float(get_setting("breakeven_target", BREAKEVEN_TARGET))
    max_special = float(get_setting("max_special_stake", 150000.0))

    with st.form("settings_form"):
        base_bankroll = st.number_input("Bankroll operativo inicial (COP)", min_value=50000.0, value=bankroll, step=1000.0)
        subscription_cost = st.number_input("Costo de suscripción al grupo (COP)", min_value=0.0, value=subscription, step=1000.0)
        breakeven_target = st.number_input("Breakeven net target (COP)", min_value=100000.0, value=breakeven, step=1000.0)
        max_special_stake = st.number_input("Stake especial máximo (COP)", min_value=50000.0, value=max_special, step=5000.0)
        if st.form_submit_button("Guardar configuración"):
            save_setting("base_bankroll", base_bankroll)
            save_setting("subscription_cost", subscription_cost)
            save_setting("breakeven_target", breakeven_target)
            save_setting("max_special_stake", max_special_stake)
            st.success("Configuración actualizada correctamente.")

    if max_special_stake > base_bankroll * 0.10:
        st.warning("Alerta roja: el stake especial supera el 10% del bankroll operativo, lo cual eleva el riesgo estructural del plan.")

    st.subheader("Reglas de staking")
    st.markdown(
        """
        - 1U Base: 2.0% del bankroll = $5.000 COP
        - 2U Moderado: 4.0% = $10.000 COP
        - 3U Alto: 6.0% = $15.000 COP
        - 4U Máximo: 10.0% = $25.000 COP
        - Whale / All-in: límite absoluto $150.000 COP, con advertencia si supera 10% del bankroll
        """
    )


def main() -> None:
    init_db()
    nav = st.sidebar.radio(
        "Navegación",
        ["Dashboard", "Registro de Apuestas", "Analítica", "AI Analyst", "Configuración"],
        index=0,
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Rushbet BankMaster Pro")
    st.sidebar.markdown("Capital management para apuestas deportivas")
    st.sidebar.caption(f"Breakeven target: ${get_setting('breakeven_target', BREAKEVEN_TARGET):,.0f} COP")

    if nav == "Dashboard":
        render_dashboard()
    elif nav == "Registro de Apuestas":
        render_bet_log()
    elif nav == "Analítica":
        render_analytics()
    elif nav == "AI Analyst":
        render_ai()
    else:
        render_settings()


if __name__ == "__main__":
    main()
