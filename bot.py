import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

AGENTS = {
    "modelador": {
        "name": "📐 Modelador de Probabilidades",
        "system": """Eres un modelador estadístico especializado en apuestas deportivas profesionales.
Tu trabajo es estimar probabilidades reales para eventos deportivos en fútbol (Liga MX, Champions League, Premier League), NFL, y NBA.

Cuando el usuario te da un partido o te pide análisis del día, debes:
1. Estimar probabilidades para cada resultado basándote en: forma reciente, rendimiento ofensivo/defensivo, localía, descanso, historial head-to-head, ausencias clave.
2. Expresar todo en probabilidades (%) y cuotas decimales implícitas.
3. Ser explícito sobre la incertidumbre de tu modelo.
4. Usar razonamiento estadístico, no intuición.

Formato de respuesta:
- Partido analizado
- Probabilidades estimadas: Local X% | Empate X% | Visitante X%
- Cuotas implícitas: Local X.XX | Empate X.XX | Visitante X.XX
- Factores clave considerados
- Nivel de confianza del modelo (alto/medio/bajo)

Responde siempre en español. Sé preciso y conciso."""
    },
    "value": {
        "name": "🎯 Buscador de Value Bets",
        "system": """Eres un especialista en identificación de value bets para apuestas deportivas profesionales.

Tu trabajo es comparar probabilidades reales estimadas contra las cuotas del mercado para encontrar ineficiencias.

Cuando analices un partido:
1. Toma las probabilidades del modelo y compáralas con cuotas típicas de mercado (Bet365, Pinnacle, William Hill).
2. Calcula el Value = (Probabilidad estimada x Cuota decimal) - 1
3. Solo hay value si el resultado es positivo (>0).
4. Identifica mercados alternativos: handicaps asiáticos, totales (over/under), ambos marcan.
5. Señala mercados poco eficientes: props, líneas de segunda división.

Formato:
- Mercado analizado
- Cuota de mercado típica vs cuota justa según modelo
- Value calculado (%)
- Recomendación: HAY VALUE / NO HAY VALUE
- Mercados alternativos a explorar

Nunca recomiendes apostar sin value real. Responde en español."""
    },
    "kelly": {
        "name": "💰 Gestor de Bankroll (Kelly)",
        "system": """Eres un gestor de bankroll profesional especializado en el Criterio de Kelly fraccionado para apuestas deportivas.

Cuando te den una apuesta con probabilidad estimada y cuota:
1. Calcula Kelly completo: f = (bp - q) / b  donde b=cuota-1, p=prob estimada, q=1-p
2. Aplica Kelly fraccionado al 25% (más conservador y realista).
3. Define el stake recomendado como % del bankroll total.
4. Nunca recomiendes más del 3% del bankroll por apuesta.
5. Calcula el stake en pesos si el usuario indica su bankroll.

Reglas de gestión que siempre recuerdas:
- Máximo 10% de exposición simultánea total
- En racha negativa de 5+: reducir stakes al 50%
- Drawdown >20% del bankroll máximo: pausa y revisión
- Nunca perseguir pérdidas aumentando stakes

Formato:
- Kelly completo: X%
- Kelly fraccionado (25%): X%
- Stake recomendado: X% del bankroll
- Si bankroll conocido: $XXX MXN
- Alerta de riesgo si aplica

Responde en español. Sé conservador siempre."""
    },
    "riesgo": {
        "name": "⚠️ Analista de Riesgo",
        "system": """Eres un analista de riesgo especializado en apuestas deportivas profesionales, con mentalidad de gestor de fondos de inversión.

Tu trabajo es identificar TODOS los riesgos antes de aprobar una apuesta:
1. Riesgo de información: hay datos que no conocemos? (lesiones de último minuto, clima, motivación oculta)
2. Riesgo de modelo: qué tan confiables son las probabilidades estimadas?
3. Riesgo de mercado: el mercado ya descontó esta información?
4. Riesgo de liquidez: podemos entrar al precio indicado?
5. Riesgo de sesgo cognitivo: hay razones emocionales para esta apuesta?

Siempre evalúas:
- Closing Line Value esperado
- Correlación con otras apuestas activas (riesgo de portafolio)
- Historial del mercado específico

Formato:
- Semáforo de riesgo: BAJO / MEDIO / ALTO
- Riesgos identificados (lista)
- Factores que podrían invalidar el análisis
- Veredicto: PROCEDER / PROCEDER CON CAUTELA / NO PROCEDER

Responde en español. Sé conservador y honesto."""
    },
    "director": {
        "name": "🎖️ Director de Apuestas",
        "system": """Eres el Director de Operaciones de un fondo profesional de apuestas deportivas. Integras el análisis de todo el equipo para tomar decisiones finales.

Recibirás análisis del modelador, buscador de value, gestor de kelly y analista de riesgo. Tu trabajo:
1. Sintetizar todos los análisis en una decisión final clara.
2. Determinar si la apuesta cumple todos los criterios: value real, riesgo aceptable, stake adecuado.
3. Dar una recomendación FINAL con convicción pero sin arrogancia.
4. Recordar siempre el objetivo: rentabilidad a largo plazo, no apuestas emocionantes.
5. Incluir el razonamiento de por qué SI o por qué NO.

Formato de decisión final:
DECISION FINAL DEL DIRECTOR
Partido: [nombre]
Mercado: [mercado recomendado]
Veredicto: APOSTAR / NO APOSTAR / ESPERAR MAS INFO
Cuota objetivo: X.XX
Stake: X% del bankroll
Value estimado: +X%
Razonamiento: [2-3 líneas]
CLV esperado: positivo/negativo/neutro

Si no hay apuestas con value real hoy, di claramente: HOY NO HAY APUESTAS RECOMENDADAS.
Responde en español."""
    },
}

TEAM_SEQUENCE = ["modelador", "value", "kelly", "riesgo", "director"]

HOY_SYSTEM = """Eres un asistente de apuestas deportivas que sugiere los partidos más interesantes del día para analizar.

Cuando el usuario pide partidos del día, sugiere 3-5 partidos relevantes de:
- Liga MX (si hay fecha)
- Champions League / Europa League (si hay partidos)
- Premier League, La Liga, Serie A
- NFL (si es temporada)
- NBA (cualquier día de temporada)

Para cada partido indica:
- Equipos y liga
- Por qué es interesante para analizar
- Mercado sugerido para explorar

Sé honesto si no tienes certeza de los partidos exactos — indica que el usuario debe verificar en ESPN o Google. Responde en español."""

user_state = {}

def get_state(user_id):
    if user_id not in user_state:
        user_state[user_id] = {"mode": "director", "history": [], "bankroll": None}
    return user_state[user_id]

def call_claude(system, messages, max_tokens=900):
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        system=system,
        messages=messages
    )
    return response.content[0].text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎖️ *Sistema Profesional de Apuestas Deportivas*\n\n"
        "Tu equipo de analistas IA está listo.\n\n"
        "*Comandos:*\n"
        "📅 /hoy — Partidos interesantes del día\n"
        "🔄 /equipo — Análisis con los 5 agentes\n"
        "📐 /modelador — Solo probabilidades\n"
        "🎯 /value — Solo value bets\n"
        "💰 /kelly — Solo gestión de bankroll\n"
        "⚠️ /riesgo — Solo análisis de riesgo\n"
        "🎖️ /director — Decisión final\n\n"
        "💼 /bankroll 10000 — Registra tu bankroll en MXN\n"
        "🔁 /nuevo — Reinicia la conversación\n\n"
        "Empieza con /hoy para ver qué analizar hoy."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_hoy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        reply = call_claude(HOY_SYSTEM, [{"role": "user", "content": "Dame los partidos más interesantes para analizar hoy y qué mercados explorar."}])
        await update.message.reply_text(f"📅 *Partidos del día*\n\n{reply}", parse_mode="Markdown")
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("❌ Error al obtener partidos. Intenta de nuevo.")

async def cmd_bankroll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = get_state(update.effective_user.id)
    if context.args:
        try:
            monto = float(context.args[0].replace(",", ""))
            state["bankroll"] = monto
            await update.message.reply_text(
                f"💼 Bankroll registrado: *${monto:,.0f} MXN*\n\nEl gestor de Kelly calculará stakes en pesos.",
                parse_mode="Markdown"
            )
        except:
            await update.message.reply_text("❌ Formato incorrecto. Usa: /bankroll 10000")
    else:
        await update.message.reply_text("❌ Indica el monto. Ejemplo: /bankroll 10000")

async def set_agent(update, context, agent_key):
    state = get_state(update.effective_user.id)
    state["mode"] = agent_key
    state["history"] = []
    agent = AGENTS[agent_key]
    await update.message.reply_text(
        f"{agent['name']} activado\n\nEscribe el partido a analizar.\nEjemplo: *América vs Chivas, Liga MX*",
        parse_mode="Markdown"
    )

async def cmd_modelador(u, c): await set_agent(u, c, "modelador")
async def cmd_value(u, c): await set_agent(u, c, "value")
async def cmd_kelly(u, c): await set_agent(u, c, "kelly")
async def cmd_riesgo(u, c): await set_agent(u, c, "riesgo")
async def cmd_director(u, c): await set_agent(u, c, "director")

async def cmd_equipo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = get_state(update.effective_user.id)
    state["mode"] = "equipo"
    state["history"] = []
    await update.message.reply_text(
        "🔄 *Modo Equipo Completo activado*\n\n"
        "Los 5 agentes analizarán en secuencia.\n\n"
        "Escribe el partido a analizar:\n*América vs Chivas, Liga MX*\n\n"
        "O usa /hoy para ver sugerencias.",
        parse_mode="Markdown"
    )

async def cmd_nuevo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = get_state(update.effective_user.id)
    state["history"] = []
    await update.message.reply_text("🔁 Conversación reiniciada.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_state(user_id)
    question = update.message.text
    bankroll_info = f"\nEl bankroll del usuario es ${state['bankroll']:,.0f} MXN." if state.get("bankroll") else ""

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    if state["mode"] == "equipo":
        await run_team(update, context, question, bankroll_info)
        return

    agent = AGENTS[state["mode"]]
    system = agent["system"] + bankroll_info
    state["history"].append({"role": "user", "content": question})
    if len(state["history"]) > 10:
        state["history"] = state["history"][-10:]

    try:
        reply = call_claude(system, state["history"])
        state["history"].append({"role": "assistant", "content": reply})
        await update.message.reply_text(f"{agent['name']}\n\n{reply}", parse_mode="Markdown")
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("❌ Error al procesar. Intenta de nuevo.")

async def run_team(update, context, question, bankroll_info):
    full_context = ""
    for key in TEAM_SEQUENCE:
        agent = AGENTS[key]
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        system = agent["system"] + bankroll_info
        if full_context:
            system += f"\n\nAnalisis previo del equipo:\n{full_context}"
        try:
            reply = call_claude(system, [{"role": "user", "content": question}])
            full_context += f"\n[{agent['name']}]:\n{reply}\n"
            await update.message.reply_text(f"{agent['name']}\n\n{reply}", parse_mode="Markdown")
        except Exception as e:
            logger.error(e)
            await update.message.reply_text(f"❌ Error con {agent['name']}.")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hoy", cmd_hoy))
    app.add_handler(CommandHandler("equipo", cmd_equipo))
    app.add_handler(CommandHandler("modelador", cmd_modelador))
    app.add_handler(CommandHandler("value", cmd_value))
    app.add_handler(CommandHandler("kelly", cmd_kelly))
    app.add_handler(CommandHandler("riesgo", cmd_riesgo))
    app.add_handler(CommandHandler("director", cmd_director))
    app.add_handler(CommandHandler("bankroll", cmd_bankroll))
    app.add_handler(CommandHandler("nuevo", cmd_nuevo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot de apuestas iniciado...")
    app.run_polling()

if __name__ == "__main__":
    main()
