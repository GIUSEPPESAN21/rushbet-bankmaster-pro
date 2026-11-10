import os
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv()


def _fallback_insight(bets: List[dict], bankroll: float, prompt: str) -> str:
    total_wins = sum(1 for bet in bets if bet.get("result") == "won")
    total_losses = sum(1 for bet in bets if bet.get("result") == "lost")
    net_profit = sum(float(bet.get("net_profit", 0.0)) for bet in bets)
    sport_breakdown = {}
    for bet in bets:
        sport_breakdown[bet.get("sport", "Sin sport")] = sport_breakdown.get(bet.get("sport", "Sin sport"), 0) + float(bet.get("stake", 0.0))

    lines = [
        "Análisis de riesgo (modo local / sin Gemini):",
        f"- Bankroll operativo actual: ${bankroll:,.0f} COP",
        f"- Apuestas analizadas: {len(bets)}",
        f"- Ganadas: {total_wins} | Perdidas: {total_losses}",
        f"- Net Profit acumulado: ${net_profit:,.0f} COP",
        "- Distribución de riesgo por deporte:",
    ]
    for sport, stake in sport_breakdown.items():
        lines.append(f"  • {sport}: ${stake:,.0f} COP en riesgo")
    lines.append("")
    lines.append("Recomendación:")
    lines.append("- Mantén stakes por debajo de 10% del bankroll operativo en jugadas de máximo riesgo.")
    lines.append("- Prioriza apuestas con edge positivo y confianza > 80%.")
    lines.append("- Si el net profit está por debajo de la meta de breakeven, reduce el volumen 25% y compensa con selección más estricta.")
    lines.append(f"- Prompt del usuario: {prompt}")
    return "\n".join(lines)


def generate_analysis_report(bets: List[dict], bankroll: float, prompt: str = "") -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return _fallback_insight(bets, bankroll, prompt)

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        summary = []
        for bet in bets:
            summary.append(
                f"- {bet.get('bet_date')} | {bet.get('sport')} | {bet.get('market')} | {bet.get('selection')} | odds {bet.get('odds')} | stake {bet.get('stake')} | status {bet.get('status')} | net_profit {bet.get('net_profit')}"
            )

        user_prompt = prompt or (
            "Actúa como un analista financiero de apuestas deportivas. Resume el rendimiento, identifica riesgos, y propone estrategia de staking."
        )
        full_prompt = f"""
        {user_prompt}

        Contexto:
        - Bankroll operativo actual: {bankroll:,.0f} COP
        - Meta de breakeven: 370.000 COP
        - Motores a considerar: ROI, Yield, Win rate, Kelly, tamaño de stake, riesgo por apuesta.
        - Registro de apuestas:
        {chr(10).join(summary) if summary else 'Sin apuestas registradas.'}

        Responde en español, con claridad ejecutiva, recomendaciones cuantitativas y un plan de acción concreto para la próxima sesión.
        """

        response = model.generate_content(full_prompt)
        return response.text
    except Exception:
        return _fallback_insight(bets, bankroll, prompt)
