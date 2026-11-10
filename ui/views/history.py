"""Historial: filtros, liquidación rápida, edición, borrado con confirmación y respaldo CSV."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from core import database as db
from core.models import STATUSES, UNIT_TYPES
from ui import components as ui
from ui.state import load


def render() -> None:
    bets, cfg = load()
    c = cfg.currency
    ui.show_flash()
    pending = [b for b in bets if b["status"] == "pending"]
    ui.page_header("Historial de apuestas", "Liquida, corrige y respalda tu registro.", "receipt_long",
                   badges=[{"text": f"{len(bets)} registradas", "tone": "neutral"},
                           {"text": f"{len(pending)} pendientes", "tone": "info" if pending else "success"}])

    if not bets:
        ui.empty_state("Sin apuestas", "Cuando registres apuestas aparecerán aquí.", "inbox")
        _backup(bets)
        return

    tab_pending, tab_all, tab_backup = st.tabs([f":material/schedule: Pendientes ({len(pending)})",
                                                ":material/table_view: Todas", ":material/cloud_download: Respaldo"])
    with tab_pending:
        _pending(pending, c)
    with tab_all:
        _all(bets, c)
    with tab_backup:
        _backup(bets)


def _pending(pending, c) -> None:
    if not pending:
        ui.empty_state("Todo liquidado", "No hay apuestas abiertas.", "task_alt")
        return
    for bet in pending:
        with st.container(border=True):
            info, actions = st.columns([1.6, 1])
            info.markdown(f"**{bet['event_name']}** · {bet['selection']}")
            info.caption(f"{bet['bet_date']} · {bet['sport']} · {bet['market']} · @{bet['odds']:.2f} · "
                         f"{bet['unit_type']} · stake {ui.money(bet['stake'], c)} · gana {ui.money(bet['stake'] * (bet['odds'] - 1), c)}")
            b1, b2, b3 = actions.columns(3)
            for col, status, label, icon in ((b1, "won", "Ganada", "check_circle"), (b2, "lost", "Perdida", "cancel"),
                                             (b3, "void", "Nula", "remove_circle")):
                if col.button(label, key=f"settle_{status}_{bet['id']}", icon=f":material/{icon}:", width="stretch"):
                    db.settle_bet(bet["id"], status)
                    ui.flash(f"#{bet['id']} liquidada como {STATUSES[status].lower()}.")
                    st.rerun()


def _all(bets, c) -> None:
    df = pd.DataFrame(bets)
    f1, f2, f3, f4 = st.columns([1, 1, 1, 1.3])
    sports = f1.multiselect("Deporte", sorted(df["sport"].unique()))
    statuses = f2.multiselect("Estado", list(STATUSES), format_func=STATUSES.get)
    units = f3.multiselect("Unidad", sorted(df["unit_type"].unique()))
    text = f4.text_input("Buscar", placeholder="Evento, selección o nota", key="hist_search")
    if sports:
        df = df[df["sport"].isin(sports)]
    if statuses:
        df = df[df["status"].isin(statuses)]
    if units:
        df = df[df["unit_type"].isin(units)]
    if text:
        needle = text.lower()
        df = df[df[["event_name", "selection", "notes", "market"]].fillna("").apply(
            lambda r: needle in " ".join(r).lower(), axis=1)]

    st.caption(f"{len(df)} apuestas · neto filtrado {ui.money(df['net_profit'].sum(), c, signed=True)}")
    view = df.assign(estado=df["status"].map(STATUSES))[
        ["id", "bet_date", "sport", "event_name", "selection", "market", "odds", "stake", "unit_type", "estado", "net_profit"]]
    st.dataframe(
        view, width="stretch", hide_index=True,
        column_config={
            "id": st.column_config.NumberColumn("#", width="small"),
            "bet_date": "Fecha", "sport": "Deporte", "event_name": "Evento", "selection": "Selección", "market": "Mercado",
            "odds": st.column_config.NumberColumn("Cuota", format="%.2f"),
            "stake": st.column_config.NumberColumn("Stake", format="$%,.0f"),
            "unit_type": "Unidad", "estado": "Estado",
            "net_profit": st.column_config.NumberColumn("Neto", format="$%,.0f"),
        },
    )

    ui.section_title("Editar o eliminar", "edit")
    options = {int(b["id"]): f"#{b['id']} · {b['bet_date']} · {b['event_name']} · {b['selection']}" for b in bets}
    bet_id = st.selectbox("Apuesta", list(options), format_func=options.get, key="hist_pick")
    bet = db.get_bet(bet_id)
    if bet:
        _edit_form(bet)


def _edit_form(bet) -> None:
    with st.form(f"edit_{bet['id']}"):
        a, b, d = st.columns(3)
        bet_date = a.date_input("Fecha", value=date.fromisoformat(bet["bet_date"][:10]), format="YYYY-MM-DD")
        sport = b.text_input("Deporte", bet["sport"])
        market = d.text_input("Mercado", bet["market"])
        event = a.text_input("Evento", bet["event_name"])
        selection = b.text_input("Selección", bet["selection"])
        odds = d.number_input("Cuota", min_value=1.01, value=float(bet["odds"]), step=0.05, format="%.2f")
        stake = a.number_input("Stake", min_value=1.0, value=float(bet["stake"]), step=1000.0, format="%.0f")
        confidence = b.slider("Confianza (%)", 0, 100, int(bet["confidence"]))
        unit = d.selectbox("Unidad", UNIT_TYPES, index=UNIT_TYPES.index(bet["unit_type"]) if bet["unit_type"] in UNIT_TYPES else 0)
        status = a.selectbox("Estado", list(STATUSES), index=list(STATUSES).index(bet["status"]), format_func=STATUSES.get)
        closing = b.number_input("Cuota de cierre", min_value=0.0, value=float(bet["closing_odds"] or 0), step=0.05, format="%.2f")
        notes = st.text_area("Notas", bet["notes"] or "", height=70)
        confirm = st.checkbox("Confirmo que quiero eliminar esta apuesta")
        save_col, del_col = st.columns(2)
        save = save_col.form_submit_button("Guardar cambios", type="primary", icon=":material/save:", width="stretch")
        delete = del_col.form_submit_button("Eliminar", icon=":material/delete:", width="stretch")
    if save:
        try:
            db.update_bet(bet["id"], bet_date=bet_date.isoformat(), sport=sport, market=market, event_name=event,
                          selection=selection, odds=odds, stake=stake, confidence=confidence, unit_type=unit,
                          status=status, closing_odds=closing or None, notes=notes)
        except ValueError as exc:
            st.error(str(exc), icon=":material/error:")
        else:
            ui.flash(f"Apuesta #{bet['id']} actualizada.")
            st.rerun()
    if delete:
        if not confirm:
            st.warning("Marca la casilla de confirmación para eliminar.", icon=":material/warning:")
        else:
            db.delete_bet(bet["id"])
            ui.flash(f"Apuesta #{bet['id']} eliminada.", "warning")
            st.rerun()


def _backup(bets) -> None:
    ui.section_title("Respaldo", "cloud_download",
                     "En Streamlit Community Cloud el disco se borra al reiniciar: descarga el CSV con frecuencia.")
    st.download_button("Descargar historial CSV", db.export_csv(bets), file_name=f"bankmaster_{date.today():%Y%m%d}.csv",
                       mime="text/csv", icon=":material/download:", disabled=not bets)
    uploaded = st.file_uploader("Importar CSV exportado", type=["csv"], key="hist_import")
    if uploaded is not None and st.button("Importar apuestas", icon=":material/upload:"):
        imported, errors = db.import_csv(uploaded.getvalue())
        if errors:
            st.warning(f"{imported} importadas, {len(errors)} con errores:\n\n" + "\n\n".join(errors[:10]),
                       icon=":material/warning:")
        else:
            ui.flash(f"{imported} apuestas importadas.")
            st.rerun()
