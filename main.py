"""
Webhook de Dialogflow ES para Game Non Stop (Paco "Cartucho").

Arrancar (desde esta carpeta, con el venv activado):
    uvicorn main:app --reload --port 8000

Despues: publicar el puerto 8000 como Public (VS Code, pestaña PORTS) y pegar la
URL + /webhook en Dialogflow -> Fulfillment.
Acordaos de activar "Enable webhook call for this intent" EN CADA INTENCION
que tenga que pasar por aqui.
"""

import asyncio
import html
import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from google import genai
from google.genai import types

load_dotenv()  # carga GOOGLE_API_KEY desde el .env

app = FastAPI()


# Datos de la tienda (inventados)
#
# En un sistema real esto seria una base de datos. Para la entrega basta con
# diccionarios: lo que se evalua es que la respuesta la decide el codigo y no
# una plantilla de Dialogflow.

# Socios: telefono -> nombre
SOCIOS = {
    "600111222": "Guillermo",
    "611222333": "Miyamoto",
    "622333444": "Hideo Kojima",
    "633444555": "Akira Toriyama",
}

# Catalogo: (juego, plataforma) -> precio y unidades. Las claves son los
# valores de referencia de las entidades @juego y @plataforma de Dialogflow.
CATALOGO = {
    ("Super Mario Bros.", "NES"): {"precio": 25, "stock": 3},
    ("Castlevania", "NES"): {"precio": 30, "stock": 0},          # agotado
    ("Metroid", "NES"): {"precio": 35, "stock": 1},
    ("The Legend of Zelda: A Link to the Past", "Super Nintendo"): {"precio": 45, "stock": 2},
    ("Donkey Kong Country", "Super Nintendo"): {"precio": 30, "stock": 2},
    ("Street Fighter II", "Super Nintendo"): {"precio": 28, "stock": 1},
    ("Sonic the Hedgehog", "Sega Mega Drive"): {"precio": 20, "stock": 3},
    ("Pokémon Red", "Game Boy"): {"precio": 40, "stock": 1},
    ("Kirby's Dream Land", "Game Boy"): {"precio": 22, "stock": 0},  # agotado
    ("Mario Kart 64", "Nintendo 64"): {"precio": 32, "stock": 2},
}

# Pedidos: telefono -> lo que han encargado y como va
PEDIDOS = {
    "600111222": {"articulo": "una Mega Drive reacondicionada", "estado": "en camino, llega el viernes"},
    "611222333": {"articulo": "The Legend of Zelda: A Link to the Past", "estado": "listo para recoger en tienda"},
    "622333444": {"articulo": "un pack de Game Boy con Pokémon Red", "estado": "pendiente de pago"},
    # 633444555 (Akira Toriyama) es socio pero no tiene pedidos
}

# Un telefono movil espanol: 6 o 7 y ocho digitos mas.
TELEFONO_RE = re.compile(r"^[67]\d{8}$")


# Utilidades

def responder(texto: str, contextos: list | None = None) -> dict:
    """Formato que espera Dialogflow ES. Las respuestas van en SSML (<speak>)
    porque el texto se va a convertir en voz."""
    respuesta = {"fulfillmentText": f"<speak>{texto}</speak>"}
    if contextos:
        respuesta["outputContexts"] = contextos
    return respuesta


def cerrar_reserva(sesion: str) -> list:
    """Pone lifespan 0 a los contextos de la reserva: equivale a cerrarlos.
    Asi, un 'si' suelto despues de un error ya no confirma nada."""
    return [
        {"name": f"{sesion}/contexts/ctx_reserva", "lifespanCount": 0},
        {"name": f"{sesion}/contexts/reservar_juego-followup", "lifespanCount": 0},
    ]


def normalizar_telefono(valor: str) -> str:
    """'612 345 678' / '612-345-678' -> '612345678'."""
    return re.sub(r"\D", "", valor or "")


# Logica de negocio: reservar un juego

def gestionar_reserva(parametros: dict, sesion: str) -> dict:
    juego = parametros.get("juego", "")
    plataforma = parametros.get("plataforma", "")
    telefono = normalizar_telefono(parametros.get("telefono", ""))

    # Camino 1: el telefono no tiene formato de movil espanol.
    # La entidad @telefono ya filtra, pero la validacion de verdad es la nuestra.
    if not TELEFONO_RE.match(telefono):
        return responder(
            "Ese número no me cuadra, que un móvil lleva nueve dígitos y empieza por 6 o por 7. "
            "Vamos a empezar de nuevo con la reserva, ¿vale?",
            cerrar_reserva(sesion),
        )

    # Camino 2: el telefono no es de un socio
    nombre = SOCIOS.get(telefono)
    if nombre is None:
        return responder(
            "No te tengo en la libreta de socios con ese teléfono. "
            "Las reservas son solo para socios del club. Apúntate en tienda y vuelves.",
            cerrar_reserva(sesion),
        )

    # Camino 3: ese juego no existe para esa consola o esta agotado
    articulo = CATALOGO.get((juego, plataforma))
    if articulo is None:
        otras = [p for (j, p) in CATALOGO if j == juego]
        if otras:
            return responder(
                f"{nombre}, {juego} no lo tengo para {plataforma}, "
                f"solo para {otras[0]}. Si quieres, reservamos esa versión.",
                cerrar_reserva(sesion),
            )
        return responder(
            f"{nombre}, de {juego} no tengo nada en la tienda ahora mismo.",
            cerrar_reserva(sesion),
        )

    if articulo["stock"] <= 0:
        return responder(
            f"{nombre}, qué mala suerte: {juego} para {plataforma} está agotadísimo. "
            "Pregúntame por otro clásico y te recomiendo algo igual de bueno.",
            cerrar_reserva(sesion),
        )

    # Camino bueno: el contexto sigue vivo y espera el si/no del follow-up
    return responder(
        f"Perfecto, {nombre}. Tengo {juego} para {plataforma} por "
        f"{articulo['precio']} euros. ¡Este juego es una joya, ya no los hacen como antes! "
        '<break time="300ms"/> ¿Te lo dejo reservado?'
    )


# Logica de negocio: estado de un pedido

def gestionar_pedido(parametros: dict) -> dict:
    telefono = normalizar_telefono(parametros.get("telefono", ""))

    nombre = SOCIOS.get(telefono)
    if nombre is None:
        return responder(
            "No encuentro ningún pedido con ese teléfono. "
            "Puede que lo haya entendido mal, ¿me lo repites?"
        )

    pedido = PEDIDOS.get(telefono)
    if pedido is None:
        return responder(f"{nombre}, ahora mismo no tienes ningún pedido abierto con nosotros.")

    return responder(
        f"{nombre}, tu pedido de {pedido['articulo']} está {pedido['estado']}."
    )


# Consultas sobre la tienda: respuesta documental (OCR + LLM)
#
# Los documentos se leyeron UNA VEZ con ocr.py y estan en datos/documentos.json.
# Aqui solo se leen del disco al arrancar: nunca hay OCR dentro de la peticion,
# porque Dialogflow corta a los 5 segundos. Son pocos y cortos, asi que se
# meten enteros en el prompt (sin base vectorial).

RUTA_DOCUMENTOS = Path(__file__).parent / "datos" / "documentos.json"
MODELO = "gemini-3.5-flash-lite"   # ~1 s; el 3.8 Flash esta saturado (503)


def cargar_documentos() -> str:
    if not RUTA_DOCUMENTOS.exists():
        print("AVISO: no existe datos/documentos.json. Ejecuta antes: python ocr.py")
        return ""
    datos = json.loads(RUTA_DOCUMENTOS.read_text(encoding="utf-8"))
    separador = "\n\n---\n\n"
    return separador.join(
        f"DOCUMENTO: {nombre}\n{d['texto']}" for nombre, d in datos.items()
    )


CONTEXTO = cargar_documentos()
print(f"Documentos cargados: {len(CONTEXTO)} caracteres\n")

cliente = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

# Dialogflow corta a los 5 s. La API de Gemini no admite timeouts de cliente
# menores de 10 s, asi que el limite lo ponemos nosotros con asyncio.wait_for.
LIMITE_LLM = 3.5

INSTRUCCIONES = """Eres Paco "Cartucho", dependiente de Game Non Stop, una tienda de videojuegos retro.
Hablas en español de España, cercano y con el humor de un friki de los 90, pero breve:
como máximo dos frases, porque tu respuesta se convierte en voz.
No uses asteriscos, listas ni formato. Di las cifras tal y como aparecen en los documentos."""

PLANTILLA = """Responde a la pregunta del cliente usando ÚNICAMENTE la información de los
DOCUMENTOS que vienen a continuación. Si la respuesta no está en los documentos,
responde exactamente con la palabra NO_LO_SE y nada más. No supongas ni completes
con conocimiento propio.

DOCUMENTOS:
{contexto}

PREGUNTA: {pregunta}"""

# Lo que dice Paco cuando el dato no esta en los documentos (control de alucinaciones)
SIN_RESPUESTA = (
    "Uy, eso no lo tengo apuntado en mis papeles, y yo no me invento nada. "
    "Pregúntame por devoluciones, garantía, tasación, el club o las consolas."
)


async def gestionar_consulta(pregunta: str) -> dict:
    if not CONTEXTO:
        return responder(SIN_RESPUESTA)

    inicio = time.time()
    # El try/except no es decorativo: si el modelo falla o tarda, hay que devolver
    # algo igualmente. Un webhook que lanza una excepcion deja al usuario en silencio.
    try:
        respuesta = await asyncio.wait_for(
            cliente.aio.models.generate_content(
                model=MODELO,
                contents=PLANTILLA.format(contexto=CONTEXTO, pregunta=pregunta),
                config=types.GenerateContentConfig(
                    system_instruction=INSTRUCCIONES,
                    temperature=0.1,
                    max_output_tokens=200,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            ),
            timeout=LIMITE_LLM,
        )
        texto = (respuesta.text or "").strip()
    except Exception as e:
        print("ERROR LLM:", type(e).__name__, e)
        return responder("Se me ha colgado el cartucho un momento. ¿Me lo repites?")

    print(f"LLM ({time.time() - inicio:.1f}s): {texto!r}")

    if not texto or "NO_LO_SE" in texto:
        return responder(SIN_RESPUESTA)

    # Quitamos formato y escapamos &, < y >, que romperian el SSML
    return responder(html.escape(texto.replace("*", ""), quote=False))


# Endpoint

@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()

    resultado = body["queryResult"]
    intencion = resultado["intent"]["displayName"]
    parametros = resultado.get("parameters", {})
    pregunta = resultado.get("queryText", "")
    sesion = body.get("session", "")

    # Imprimimos siempre lo que llega: es lo que mas ayuda a depurar
    print("-" * 50)
    print("INTENCION:", intencion)
    print("PARAMETROS:", parametros)
    print("TEXTO:", pregunta)

    # Si aun faltan parametros obligatorios, dejamos que Dialogflow use sus prompts
    if not resultado.get("allRequiredParamsPresent", False):
        return {}

    if intencion == "reservar_juego":
        return gestionar_reserva(parametros, sesion)

    if intencion == "consultar_pedido":
        return gestionar_pedido(parametros)

    if intencion in ("consulta_tienda", "Default Fallback Intent"):
        return await gestionar_consulta(pregunta)

    # Nunca dejar al agente sin respuesta
    return responder("Eso todavía no sé gestionarlo, pero Paco aprende rápido.")


@app.get("/")
def raiz():
    """Para comprobar de un vistazo que el tunel llega hasta aqui."""
    return {"estado": "ok", "tienda": "Game Non Stop"}
