"""
Bot de Telegram para Paco "Cartucho" (Game Non Stop).

Telegram (voz o texto) -> Dialogflow (STT + intenciones + webhook) -> respuesta
en texto y, si el usuario hablo, tambien en voz con ElevenLabs.

Arrancar (con el venv activado y el webhook levantado en otra terminal):
    python bot_telegram.py

Usa polling: el bot pregunta a Telegram por mensajes nuevos, asi que no hace
falta ninguna URL publica para esta parte.
"""

import asyncio
import html
import os
import re
import time
import uuid

import requests
from dotenv import load_dotenv
from google.cloud import dialogflow
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
PROJECT_ID = os.environ["DIALOGFLOW_PROJECT_ID"]
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")
ELEVENLABS_MODELO = "eleven_multilingual_v2"

IDIOMA = "es"
FRASE_ERROR = "Se me ha colgado el cartucho un momento. ¿Me lo repites?"
FRASE_NO_OIDO = "Uy, no te he pillado bien, ¿me lo repites?"

dialogflow_cliente = dialogflow.SessionsClient()

# El SESSION_ID identifica la CONVERSACION: los contextos de Dialogflow (la
# reserva en curso) viven colgados de el. Uno por chat; /start lo renueva.
SESIONES: dict[int, str] = {}


def sesion_de(chat_id: int) -> str:
    if chat_id not in SESIONES:
        SESIONES[chat_id] = f"tg-{chat_id}-{uuid.uuid4().hex[:8]}"
    return dialogflow_cliente.session_path(PROJECT_ID, SESIONES[chat_id])


# Texto de las respuestas: el agente contesta en SSML (<speak>, <break>...)

def para_texto(ssml: str) -> str:
    """Quita todas las etiquetas SSML: Telegram muestra solo el texto."""
    sin_etiquetas = html.unescape(re.sub(r"<[^>]+>", "", ssml))
    return re.sub(r"[ 	]{2,}", " ", sin_etiquetas).strip()


def para_voz(ssml: str) -> str:
    """ElevenLabs entiende <break time="0.3s" />, pero no <speak> ni <emphasis>."""
    texto = re.sub(
        r'<break time="(\d+)ms"\s*/>',
        lambda m: f'<break time="{int(m.group(1)) / 1000:.1f}s" />',
        ssml,
    )
    return re.sub(r"</?(speak|emphasis)[^>]*>", "", texto).strip()


# Dialogflow

def preguntar_a_dialogflow(chat_id: int, texto: str | None = None,
                           audio: bytes | None = None, evento: str | None = None):
    """Manda texto, audio (OGG/Opus de Telegram) o un evento al agente."""
    if audio is not None:
        entrada = dialogflow.QueryInput(audio_config=dialogflow.InputAudioConfig(
            audio_encoding=dialogflow.AudioEncoding.AUDIO_ENCODING_OGG_OPUS,
            sample_rate_hertz=48000,         # las notas de voz de Telegram van a 48 kHz
            language_code=IDIOMA,
        ))
    elif evento is not None:
        entrada = dialogflow.QueryInput(event=dialogflow.EventInput(name=evento, language_code=IDIOMA))
    else:
        entrada = dialogflow.QueryInput(text=dialogflow.TextInput(text=texto, language_code=IDIOMA))

    peticion = {
        "session": sesion_de(chat_id),
        "query_input": entrada,
        # Pedimos tambien el audio nativo de Dialogflow: es la voz de respaldo
        # si ElevenLabs falla.
        "output_audio_config": dialogflow.OutputAudioConfig(
            audio_encoding=dialogflow.OutputAudioEncoding.OUTPUT_AUDIO_ENCODING_OGG_OPUS
        ),
    }
    if audio is not None:
        peticion["input_audio"] = audio
    return dialogflow_cliente.detect_intent(request=peticion)


# ElevenLabs

def sintetizar(ssml: str) -> bytes | None:
    """Devuelve un MP3 con la voz de Paco, o None si ElevenLabs falla."""
    if not ELEVENLABS_API_KEY or not ELEVENLABS_VOICE_ID:
        return None
    try:
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            json={"text": para_voz(ssml), "model_id": ELEVENLABS_MODELO},
            timeout=15,
        )
        if r.status_code == 200:
            return r.content
        print("ELEVENLABS ERROR:", r.status_code, r.text[:150])
    except Exception as e:
        print("ELEVENLABS ERROR:", type(e).__name__, e)
    return None


# Respuesta al usuario

async def responder(update: Update, respuesta, con_voz: bool):
    resultado = respuesta.query_result
    ssml = resultado.fulfillment_text or FRASE_NO_OIDO

    print(f"  intencion: {resultado.intent.display_name} ({resultado.intent_detection_confidence:.2f})")
    print(f"  parametros: {dict(resultado.parameters)}")

    await update.message.reply_text(para_texto(ssml))
    if not con_voz:
        return

    inicio = time.time()
    mp3 = await asyncio.to_thread(sintetizar, ssml)
    if mp3:
        print(f"  voz: ElevenLabs ({time.time() - inicio:.1f}s)")
        await update.message.reply_voice(mp3)
    elif respuesta.output_audio:
        print("  voz: Dialogflow (respaldo)")
        await update.message.reply_voice(respuesta.output_audio)


# Manejadores de Telegram

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    SESIONES.pop(chat_id, None)                      # conversacion nueva
    print(f"\n[{chat_id}] /start")
    try:
        respuesta = await asyncio.to_thread(preguntar_a_dialogflow, chat_id, evento="WELCOME")
        await responder(update, respuesta, con_voz=True)
    except Exception as e:
        print("ERROR:", type(e).__name__, e)
        await update.message.reply_text(FRASE_ERROR)


async def texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    print(f"\n[{chat_id}] texto: {update.message.text!r}")
    try:
        respuesta = await asyncio.to_thread(preguntar_a_dialogflow, chat_id, texto=update.message.text)
        await responder(update, respuesta, con_voz=False)
    except Exception as e:
        print("ERROR:", type(e).__name__, e)
        await update.message.reply_text(FRASE_ERROR)


async def voz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    inicio = time.time()
    try:
        archivo = await update.message.voice.get_file()
        audio = bytes(await archivo.download_as_bytearray())
        respuesta = await asyncio.to_thread(preguntar_a_dialogflow, chat_id, audio=audio)
        # query_text es el speech-to-text: viene dentro del mismo detect_intent
        print(f"\n[{chat_id}] voz: {respuesta.query_result.query_text!r} ({time.time() - inicio:.1f}s hasta Dialogflow)")
        if not respuesta.query_result.query_text:
            await update.message.reply_text(FRASE_NO_OIDO)
            return
        await responder(update, respuesta, con_voz=True)
        print(f"  total: {time.time() - inicio:.1f}s")
    except Exception as e:
        print("ERROR:", type(e).__name__, e)
        await update.message.reply_text(FRASE_ERROR)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, voz))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, texto))
    print("Paco está en la tienda. Ctrl+C para cerrar.")
    app.run_polling()


if __name__ == "__main__":
    main()
