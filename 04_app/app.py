"""
app.py — Backend de la Isla de los Dinosaurios.

Flujo: Modelo de caracteres -> Nombre -> Ollama -> Identidad -> Imagen -> Chat

Variables de entorno (ver .env.example):
  OLLAMA_URL      URL pública de Ollama (ngrok en SageMaker), p. ej. https://xxx.ngrok-free.app
  OLLAMA_MODEL    modelo descargado en Ollama, p. ej. llama3.2:3b
  IMAGEN_URL      URL pública del servicio de imagen en Colab
  MODEL_PATH      ruta del checkpoint del modelo de caracteres (default model/dino_rnn.pt)
"""
import json
import os
import re
import uuid
from collections import OrderedDict
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from char_model import cargar_checkpoint, generar_nombre

BASE = Path(__file__).parent
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
IMAGEN_URL = os.getenv("IMAGEN_URL", "http://localhost:8000").rstrip("/")
MODEL_PATH = os.getenv("MODEL_PATH", str(BASE / "model" / "dino_rnn.pt"))
TIMEOUT = httpx.Timeout(300.0, connect=15.0)
HEADERS = {"ngrok-skip-browser-warning": "1"}   # evita la página de aviso de ngrok

# ---------------------------------------------------------------- modelo RNN
# Se carga UNA vez al iniciar. "Nuevo dinosaurio" solo genera; nunca reentrena.
modelo, ck = cargar_checkpoint(MODEL_PATH)
STOI, ITOS, T = ck["stoi"], ck["itos"], ck["T"]
NOMBRES_REALES = set(ck["nombres_reales"])
MUESTREO = ck.get("muestreo", {"temperatura": 0.8, "top_k": 0, "top_p": 0.9})
INFO_MODELO = {
    **ck["config"], **ck["metricas"], "muestreo": MUESTREO,
    "vocabulario": len(ITOS), "T": T, "nombres_entrenamiento": len(NOMBRES_REALES),
}

# Dinosaurios de la sesión (en memoria). Cada uno guarda su imagen UNA vez.
DINOS: "OrderedDict[str, dict]" = OrderedDict()
MAX_DINOS = 50

# ---------------------------------------------------------------- prompts
ESQUEMA = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in (
        "nombre", "significado_nombre", "apariencia", "habitat", "alimentacion",
        "comportamiento", "rasgo_distintivo", "prompt_imagen")},
    "required": ["nombre", "significado_nombre", "apariencia", "habitat", "alimentacion",
                 "comportamiento", "rasgo_distintivo", "prompt_imagen"],
}

SISTEMA_IDENTIDAD = """Eres un paleontólogo creativo que describe especies de dinosaurios FICTICIAS.
Responde solo con JSON válido en español (excepto prompt_imagen, que va en inglés).
Reglas:
- Usa el nombre para inspirar los rasgos. Pistas de raíces reales: -saurus (lagarto), -raptor (ladrón/cazador),
  -odon (diente), -venator (cazador), -ceratops (cara con cuernos), -don, -onyx (garra), mega- (grande), micro- (pequeño).
- Todos los rasgos deben ser coherentes entre sí (p. ej., dientes de carnívoro => dieta carnívora).
- Cada campo: 1 a 3 frases concretas (tamaño en metros, colores, texturas, lugar, presas o plantas).
- rasgo_distintivo: una sola característica única y visible.
- prompt_imagen: máximo 40 palabras en inglés, describe solo lo visual (cuerpo, colores, rasgo distintivo, entorno)."""

PIDE_IMAGEN = re.compile(
    r"(descr[ií]b|descripci[oó]n|pres[eé]nta|presentaci[oó]n|qui[eé]n eres|c[oó]mo eres|"
    r"c[oó]mo te ves|c[oó]mo luces|tu aspecto|apariencia|foto|imagen|mu[eé]str|ver te|verte)",
    re.IGNORECASE,
)


def sistema_chat(identidad: dict) -> str:
    ficha = "\n".join(f"- {k}: {v}" for k, v in identidad.items() if k != "prompt_imagen")
    return f"""Eres {identidad['nombre']}, un dinosaurio ficticio que habla con visitantes de la Isla de los Dinosaurios.
Esta es tu identidad oficial. Es la verdad sobre ti y NUNCA debes contradecirla:
{ficha}

Reglas:
- Habla en español, en primera persona, con personalidad acorde a tu comportamiento.
- Respuestas de máximo 100 palabras.
- Puedes inventar detalles nuevos (anécdotas, gustos, familia) siempre que sean coherentes con tu identidad.
- Si el visitante afirma algo que contradice tu identidad (otra dieta, otro hábitat, otro aspecto), corrígelo con amabilidad.
- No digas que eres una IA ni un modelo de lenguaje."""


# ---------------------------------------------------------------- servicios
async def ollama_chat(mensajes, formato=None, num_predict=300, temperatura=0.7):
    cuerpo = {"model": OLLAMA_MODEL, "messages": mensajes, "stream": False,
              "options": {"temperature": temperatura, "num_predict": num_predict}}
    if formato:
        cuerpo["format"] = formato
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS) as cli:
            r = await cli.post(f"{OLLAMA_URL}/api/chat", json=cuerpo)
            r.raise_for_status()
            return r.json()["message"]["content"]
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Ollama no respondió ({OLLAMA_URL}): {e}") from e


async def crear_identidad(nombre: str) -> dict:
    mensajes = [{"role": "system", "content": SISTEMA_IDENTIDAD},
                {"role": "user", "content": f"Crea la identidad del dinosaurio ficticio llamado {nombre}."}]
    for _ in range(2):   # un reintento si el JSON llega mal
        texto = await ollama_chat(mensajes, formato=ESQUEMA, num_predict=700)
        try:
            identidad = json.loads(texto)
            identidad["nombre"] = nombre
            return identidad
        except json.JSONDecodeError:
            continue
    raise HTTPException(502, "Ollama devolvió una identidad que no es JSON válido.")


def prompt_imagen(identidad: dict) -> str:
    base = identidad.get("prompt_imagen") or identidad.get("apariencia", "")
    return f"{identidad['nombre']} dinosaur, {base}, full body, natural history illustration, detailed"


async def generar_imagen(prompt: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS) as cli:
            r = await cli.post(f"{IMAGEN_URL}/generar", json={"prompt": prompt, "semilla": 0})
            r.raise_for_status()
            d = r.json()
            return f"data:{d.get('mime', 'image/png')};base64,{d['image_base64']}"
    except httpx.HTTPError as e:
        raise HTTPException(502, f"El servicio de imagen no respondió ({IMAGEN_URL}): {e}") from e


def nombre_nuevo() -> str:
    usados = {d["nombre"].lower() for d in DINOS.values()}
    for _ in range(200):
        n = generar_nombre(modelo, STOI, ITOS, T + 5, MUESTREO["temperatura"],
                           MUESTREO["top_k"], MUESTREO["top_p"])
        if 5 <= len(n) <= 18 and n not in NOMBRES_REALES and n not in usados:
            return n.capitalize()
    raise HTTPException(500, "No se pudo generar un nombre nuevo.")


def obtener(dino_id: str) -> dict:
    if dino_id not in DINOS:
        raise HTTPException(404, "Dinosaurio no encontrado. Crea uno nuevo.")
    return DINOS[dino_id]


# ---------------------------------------------------------------- API
app = FastAPI(title="Isla de los Dinosaurios")


class Mensaje(BaseModel):
    mensaje: str = ""
    presentar: bool = False


@app.get("/api/info")
def info():
    return {"modelo_nombres": INFO_MODELO, "ollama_modelo": OLLAMA_MODEL}


@app.get("/api/estado")
async def estado():
    """Comprueba que Ollama y el servicio de imagen estén accesibles."""
    res = {}
    async with httpx.AsyncClient(timeout=10, headers=HEADERS) as cli:
        for nombre, url in (("ollama", f"{OLLAMA_URL}/api/version"), ("imagen", f"{IMAGEN_URL}/salud")):
            try:
                r = await cli.get(url)
                res[nombre] = {"ok": r.status_code == 200, "detalle": r.json()}
            except Exception as e:  # noqa: BLE001
                res[nombre] = {"ok": False, "detalle": str(e)}
    return res


@app.post("/api/dinosaurios")
def nuevo_dinosaurio():
    """Paso 1: el modelo RNN ya entrenado genera un nombre (sin reentrenar)."""
    dino_id = uuid.uuid4().hex[:10]
    DINOS[dino_id] = {"id": dino_id, "nombre": nombre_nuevo(), "identidad": None,
                      "imagen": None, "historial": []}
    while len(DINOS) > MAX_DINOS:
        DINOS.popitem(last=False)
    return {"id": dino_id, "nombre": DINOS[dino_id]["nombre"]}


@app.post("/api/dinosaurios/{dino_id}/identidad")
async def identidad(dino_id: str):
    """Paso 2: Ollama crea la identidad a partir del nombre."""
    d = obtener(dino_id)
    if d["identidad"] is None:
        d["identidad"] = await crear_identidad(d["nombre"])
    return {"identidad": d["identidad"]}


@app.post("/api/dinosaurios/{dino_id}/imagen")
async def imagen(dino_id: str):
    """Paso 3: se genera la imagen UNA sola vez y se guarda para el chat."""
    d = obtener(dino_id)
    if d["identidad"] is None:
        raise HTTPException(409, "Primero hay que crear la identidad.")
    if d["imagen"] is None:
        d["prompt_imagen"] = prompt_imagen(d["identidad"])
        d["imagen"] = await generar_imagen(d["prompt_imagen"])
    return {"imagen": d["imagen"], "prompt": d.get("prompt_imagen")}


@app.post("/api/dinosaurios/{dino_id}/chat")
async def chat(dino_id: str, m: Mensaje):
    """Paso 4: chat. La identidad va como contexto (system) en CADA petición."""
    d = obtener(dino_id)
    if d["identidad"] is None:
        raise HTTPException(409, "Primero hay que crear la identidad.")

    if m.presentar:
        texto_usuario = "Preséntate ante el visitante: quién eres, cómo eres y dónde vives."
        incluir_imagen = True
    else:
        texto_usuario = m.mensaje.strip()[:1000]
        if not texto_usuario:
            raise HTTPException(400, "Mensaje vacío.")
        incluir_imagen = bool(PIDE_IMAGEN.search(texto_usuario))

    mensajes = [{"role": "system", "content": sistema_chat(d["identidad"])}]
    mensajes += d["historial"][-10:]          # últimas 5 vueltas de conversación
    mensajes.append({"role": "user", "content": texto_usuario})
    respuesta = await ollama_chat(mensajes, num_predict=250)

    d["historial"] += [{"role": "user", "content": texto_usuario},
                       {"role": "assistant", "content": respuesta}]
    return {"respuesta": respuesta, "incluir_imagen": incluir_imagen and d["imagen"] is not None}


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
