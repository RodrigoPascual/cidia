"""Prueba de transcripción con ruido industrial del servicio de voz de CidIA (servidor/asr).

Sintetiza 20 frases de planta con la voz en castellano de Windows (System.Speech, como
datos-demo/video/generar_medios.py), las mezcla con ruido industrial sintético (ruido rosa, zumbido
de motor de 50/100 Hz con armónicos y golpes periódicos de prensa) a varias relaciones señal/ruido
y las envía a POST /v1/audio/transcriptions. Mide WER, CER, acierto de términos clave (códigos,
cifras y vocabulario técnico) y tiempo de transcripción, con y sin prompt inicial de vocabulario.

Sin dependencias GPL: numpy (BSD) y la biblioteca estándar. ffmpeg LGPL, como programa externo,
solo para codificar en Opus como hace el navegador; con --formato wav no hace falta.

Uso (desde la raíz del repositorio, en Windows):
  python servidor/asr/prueba_ruido.py                          # modelo base por el túnel 127.0.0.1:18721
  python servidor/asr/prueba_ruido.py --prompt ambos            # cada audio sin y con prompt de vocabulario
  python servidor/asr/prueba_ruido.py --url http://127.0.0.1:18731/v1 --niveles 10,5
  python servidor/asr/prueba_ruido.py --tabla a.json b.json     # une resultados en una tabla Markdown
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.request
import uuid
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
SR = 16000
PAUSA_S = 0.6  # ruido antes y después de la voz, como al pulsar el botón un poco antes de hablar

# (referencia escrita, texto que dice la voz sintética, términos clave; «|» separa variantes válidas)
FRASES: list[tuple[str, str, list[str]]] = [
    ("¿Qué par de apriete lleva la brida B?", "¿Qué par de apriete lleva la brida B?",
     ["par de apriete", "brida b"]),
    ("La prensa 3 se ha atascado al cambiar el molde.", "La prensa tres se ha atascado al cambiar el molde.",
     ["prensa 3", "molde"]),
    ("Abre la instrucción IT-023, paso 4.", "Abre la instrucción, i te, cero veintitrés, paso cuatro.",
     ["IT-023", "paso 4"]),
    ("Los cuatro tornillos se aprietan en cruz a 25 newton metro.",
     "Los cuatro tornillos se aprietan en cruz a veinticinco newton metro.", ["en cruz", "25 newton metro"]),
    ("¿Cuánto tiempo dura la prueba de estanqueidad?", "¿Cuánto tiempo dura la prueba de estanqueidad?",
     ["prueba de estanqueidad"]),
    ("Tengo que consignar la prensa 3 antes de sacar el molde.",
     "Tengo que consignar la prensa tres antes de sacar el molde.", ["consignar", "prensa 3"]),
    ("El sensor S4 marca error de calibración.", "El sensor ese cuatro marca error de calibración.",
     ["sensor S4|sensor ese 4", "calibracion"]),
    ("¿A qué presión van los amarres hidráulicos, a 150 bar?",
     "¿A qué presión van los amarres hidráulicos, a ciento cincuenta bar?", ["amarres hidraulicos", "150 bar"]),
    ("Mide la cota de 12,5 milímetros con el calibre.",
     "Mide la cota de doce coma cinco milímetros con el calibre.", ["12,5 milimetros", "calibre"]),
    ("La junta tórica está cortada, ¿la cambio?", "La junta tórica está cortada, ¿la cambio?", ["junta torica"]),
    ("Pide la primera pieza a calidad antes de arrancar la serie.",
     "Pide la primera pieza a calidad antes de arrancar la serie.", ["primera pieza", "calidad"]),
    ("En la línea 2, estación E2, falta la llave dinamométrica.",
     "En la línea dos, estación e dos, falta la llave dinamométrica.",
     ["linea 2", "estacion e 2", "llave dinamometrica"]),
    ("¿Qué EPI necesito para soldar en el utillaje?", "¿Qué epi necesito para soldar en el utillaje?",
     ["EPI|EPIs", "utillaje"]),
    ("La temperatura del horno ha subido a 180 grados.",
     "La temperatura del horno ha subido a ciento ochenta grados.", ["horno", "180 grados"]),
    ("Marca los tornillos con la marca de testigo después del apriete.",
     "Marca los tornillos con la marca de testigo después del apriete.", ["marca de testigo"]),
    ("El lote 4521 tiene tres piezas rechazadas por rebaba.",
     "El lote cuatro mil quinientos veintiuno tiene tres piezas rechazadas por rebaba.", ["lote 4521", "rebaba"]),
    ("Baja el carro de la prensa al punto muerto inferior.",
     "Baja el carro de la prensa al punto muerto inferior.", ["carro", "punto muerto inferior"]),
    ("¿Dónde se registran las referencias 3-2-1 del utillaje?",
     "¿Dónde se registran las referencias tres, dos, uno, del utillaje?", ["referencias 3 2 1", "utillaje"]),
    ("Para la máquina, hay una fuga de aceite en el grupo hidráulico.",
     "Para la máquina, hay una fuga de aceite en el grupo hidráulico.", ["fuga de aceite", "grupo hidraulico"]),
    ("¿A cuántas revoluciones va el husillo con la fresa de 10 milímetros?",
     "¿A cuántas revoluciones va el husillo con la fresa de diez milímetros?",
     ["husillo", "fresa de 10 milimetros"]),
]

# Vocabulario de la planta como el que enviaría el gateway (títulos y códigos de las instrucciones de la
# semilla). Algunos términos de las frases no están (horno, husillo, fresa, lote, grupo hidráulico...),
# para ver también el efecto sobre lo que no viene en el prompt.
PROMPT_PLANTA = (
    "Metalúrgica Arlanza. Instrucciones IT-023, IT-031, IT-051, IT-061 e IT-071. Montaje de la brida B, "
    "prensa 3, línea 2, estación E2, sensor S4. Par de apriete en newton metro, llave dinamométrica, apriete "
    "en cruz, marca de testigo, junta tórica, prueba de estanqueidad. Cambio de molde, consignar la prensa, "
    "amarres hidráulicos, punto muerto inferior, primera pieza. Utillaje de soldadura, referencias 3-2-1, "
    "EPI, calibre, cota, rebaba."
)

PS_VOZ = r"""
param([string]$Lista)
Add-Type -AssemblyName System.Speech
$voz = New-Object System.Speech.Synthesis.SpeechSynthesizer
$es = $voz.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'es-*' } | Select-Object -First 1
if ($es) { $voz.SelectVoice($es.VoiceInfo.Name) } else { Write-Error 'No hay ninguna voz en castellano instalada'; exit 2 }
$voz.Rate = 1
$formato = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($t in (Get-Content -Raw -Encoding UTF8 $Lista | ConvertFrom-Json)) {
  $voz.SetOutputToWaveFile($t.salida, $formato)
  $voz.Speak($t.texto)
}
$voz.SetOutputToNull()
Write-Output $es.VoiceInfo.Name
"""

# ---------------------------------------------------------------- normalización y métricas

_UNIDADES = ("cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciseis "
             "diecisiete dieciocho diecinueve veinte veintiuno veintidos veintitres veinticuatro veinticinco "
             "veintiseis veintisiete veintiocho veintinueve").split()
_DECENAS = {3: "treinta", 4: "cuarenta", 5: "cincuenta", 6: "sesenta", 7: "setenta", 8: "ochenta", 9: "noventa"}
_CENTENAS = {1: "ciento", 2: "doscientos", 3: "trescientos", 4: "cuatrocientos", 5: "quinientos",
             6: "seiscientos", 7: "setecientos", 8: "ochocientos", 9: "novecientos"}
# Formas equivalentes que no deben contar como error (género y apócope de los números, plurales de unidades).
_CANON = {"un": "uno", "una": "uno", "veintiun": "veintiuno", "veintiuna": "veintiuno", "newtons": "newton",
          "bares": "bar", "kilogramos": "kilos", "kilogramo": "kilo", "milimetro": "milimetros",
          **{c.replace("ientos", "ientas"): c for c in _CENTENAS.values() if c.endswith("ientos")}}
_SUSTITUCIONES = [
    (r"(\d)\s*n\s*[·.\-]?\s*m\b", r"\1 newton metro"),
    (r"\bnewtons?\s*(?:por\s+)?metros?\b", "newton metro"),
    (r"(\d)\s*mm\b", r"\1 milimetros"),
    (r"(\d)\s*cm\b", r"\1 centimetros"),
    (r"(\d)\s*kg\b", r"\1 kilos"),
    (r"(\d)\s*%", r"\1 por ciento"),
    (r"(\d)\s*rpm\b", r"\1 revoluciones por minuto"),
]


def _hasta_999(n: int) -> str:
    if n < 30:
        return _UNIDADES[n]
    if n < 100:
        d, u = divmod(n, 10)
        return _DECENAS[d] + ("" if u == 0 else " y " + _UNIDADES[u])
    if n == 100:
        return "cien"
    c, r = divmod(n, 100)
    return _CENTENAS[c] + ("" if r == 0 else " " + _hasta_999(r))


def numero_a_letras(n: int) -> str:
    """Entero en castellano, sin tildes (la normalización las quita): 4521 → cuatro mil quinientos veintiuno."""
    if n < 1000:
        return _hasta_999(n)
    if n < 1_000_000:
        m, r = divmod(n, 1000)
        return ("mil" if m == 1 else _hasta_999(m) + " mil") + ("" if r == 0 else " " + _hasta_999(r))
    if n < 10**12:
        m, r = divmod(n, 1_000_000)
        return ("un millon" if m == 1 else numero_a_letras(m) + " millones") + ("" if r == 0 else " " + numero_a_letras(r))
    return " ".join(_UNIDADES[int(c)] for c in str(n))


def _digitos(tok: str) -> str:
    """«023» → «cero veintitres» (los ceros a la izquierda se leen uno a uno, como en los códigos)."""
    ceros = len(tok) - len(tok.lstrip("0"))
    resto = tok[ceros:]
    return " ".join(["cero"] * ceros + ([numero_a_letras(int(resto))] if resto else []))


def normalizar(texto: str) -> list[str]:
    """Minúsculas, sin tildes ni signos, cifras en letra y siglas deletreadas unidas («I. T.» → «it»)."""
    t = (texto or "").lower()
    t = re.sub(r"[°º]\s*c\b|[°º]", " grados ", t)
    t = unicodedata.normalize("NFC", "".join(c for c in unicodedata.normalize("NFD", t)
                                             if unicodedata.category(c) != "Mn"))
    for patron, reemplazo in _SUSTITUCIONES:
        t = re.sub(patron, reemplazo, t)
    t = re.sub(r"\b(\d{1,3})((?:\.\d{3})+)(?![\d,])", lambda m: m.group(1) + m.group(2).replace(".", ""), t)
    t = re.sub(r"(\d)[.,'](\d)", r"\1 coma \2", t)
    t = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    fichas: list[str] = []
    for tok in t.split():
        fichas += [_CANON.get(x, x) for x in (_digitos(tok).split() if tok.isdigit() else [tok])]
    salida: list[str] = []
    sigla = False
    for tok in fichas:
        letra = len(tok) == 1 and tok.isalpha() and tok not in "aeouy"  # a, e, o, u, y son palabras
        if letra and sigla:
            salida[-1] += tok
        else:
            salida.append(tok)
        sigla = letra
    return salida


def levenshtein(a: list | str, b: list | str) -> int:
    previa = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        actual = [i]
        for j, y in enumerate(b, 1):
            actual.append(min(previa[j] + 1, actual[j - 1] + 1, previa[j - 1] + (x != y)))
        previa = actual
    return previa[-1]


def contiene(fichas: list[str], termino: str) -> bool:
    for variante in termino.split("|"):
        v = normalizar(variante)
        if any(fichas[i:i + len(v)] == v for i in range(len(fichas) - len(v) + 1)):
            return True
    return False


# ---------------------------------------------------------------- audio

def buscar_ffmpeg() -> str | None:
    for exe in sorted((REPO / "servidor" / "gateway" / ".herramientas").glob("*/bin/ffmpeg.exe")):
        return str(exe)
    return shutil.which("ffmpeg")


def sintetizar(cache: Path) -> tuple[list[np.ndarray], str]:
    """Voz de Windows a 16 kHz, guardada en caché por texto para no repetir la síntesis."""
    cache.mkdir(parents=True, exist_ok=True)
    rutas = [cache / f"frase-{i:02d}-{hashlib.sha1(v.encode()).hexdigest()[:8]}.wav"
             for i, (_, v, _) in enumerate(FRASES, 1)]
    nombre_voz = cache / "voz.txt"
    faltan = [{"texto": v, "salida": str(p)} for (_, v, _), p in zip(FRASES, rutas, strict=True) if not p.exists()]
    if faltan:
        with tempfile.TemporaryDirectory(prefix="cidia-voz-") as d:
            lista, script = Path(d) / "voz.json", Path(d) / "voz.ps1"
            lista.write_text(json.dumps(faltan, ensure_ascii=False), encoding="utf-8")
            script.write_text(PS_VOZ, encoding="utf-8-sig")
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                                "-Lista", str(lista)], capture_output=True, text=True)
            if r.returncode != 0:
                sys.exit(f"La síntesis de voz ha fallado: {r.stderr.strip()[:300]}")
            nombre_voz.write_text(r.stdout.strip(), encoding="utf-8")
    audios = []
    for p in rutas:
        with wave.open(str(p)) as w:
            if w.getframerate() != SR or w.getnchannels() != 1:
                sys.exit(f"Formato inesperado en {p}")
            audios.append(np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768)
    return audios, nombre_voz.read_text(encoding="utf-8") if nombre_voz.exists() else "?"


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64)) + 1e-20))


def nivel_activo(x: np.ndarray) -> float:
    """RMS de la voz en las tramas de 20 ms con energía (a menos de 35 dB de la trama más fuerte)."""
    n = int(0.02 * SR)
    tramas = x[: len(x) // n * n].reshape(-1, n)
    e = np.mean(tramas.astype(np.float64) ** 2, axis=1)
    activas = e > e.max() * 10 ** (-35 / 10)
    return float(np.sqrt(e[activas].mean()))


def ruido_industrial(n: int, rng: np.random.Generator) -> np.ndarray:
    """Ruido rosa (45 % de la potencia) + zumbido de motor (25 %) + golpes de prensa (30 %), RMS 1."""
    t = np.arange(n) / SR
    espectro = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    espectro /= np.sqrt(np.maximum(f, 20.0))
    rosa = np.fft.irfft(espectro, n)

    f0 = 50.0 * (1 + rng.uniform(-0.004, 0.004))
    pesos = {1: 0.6, 2: 1.0, 3: 0.35, 4: 0.5, 5: 0.2, 6: 0.3}  # el 100 Hz domina (magnetostricción)
    zumbido = sum(pesos.get(k, 0.5 / k) * np.sin(2 * np.pi * f0 * k * t + rng.uniform(0, 2 * np.pi))
                  for k in range(1, 25))
    zumbido = zumbido * (1 + 0.15 * np.sin(2 * np.pi * rng.uniform(0.2, 0.6) * t))  # variación de carga

    golpes = np.zeros(n)
    largo = int(0.4 * SR)
    tt = np.arange(largo) / SR
    periodo = rng.uniform(0.9, 1.4)  # unos 45-65 golpes por minuto
    ti = rng.uniform(0, periodo)
    while ti < n / SR:
        i = int(ti * SR)
        seg = min(largo, n - i)
        impacto = rng.standard_normal(largo) * np.exp(-tt / 0.012)
        resonancia = (np.sin(2 * np.pi * 380 * tt) + 0.6 * np.sin(2 * np.pi * 1150 * tt + rng.uniform(0, 6.3))
                      + 0.3 * np.sin(2 * np.pi * 2700 * tt)) * np.exp(-tt / 0.09)
        golpe_sordo = 1.5 * np.sin(2 * np.pi * 60 * tt) * np.exp(-tt / 0.05)
        golpes[i:i + seg] += ((0.8 * impacto + resonancia + golpe_sordo) * rng.uniform(0.7, 1.0))[:seg]
        ti += periodo * (1 + rng.uniform(-0.05, 0.05))

    mezcla = sum(np.sqrt(p) * c / _rms(c) for p, c in ((0.45, rosa), (0.25, zumbido), (0.30, golpes)))
    return (mezcla / _rms(mezcla)).astype(np.float32)


def mezclar(voz: np.ndarray, ruido: np.ndarray, snr_db: float | None) -> np.ndarray:
    relleno = np.zeros(int(PAUSA_S * SR), np.float32)
    voz = np.concatenate([relleno, voz, relleno])
    voz = voz * (10 ** (-23 / 20) / nivel_activo(voz))  # voz a -23 dBFS de nivel activo
    mezcla = voz if snr_db is None else voz + ruido[: len(voz)] * (nivel_activo(voz) / 10 ** (snr_db / 20))
    pico = float(np.max(np.abs(mezcla)))
    return (mezcla * (0.99 / pico) if pico > 0.99 else mezcla).astype(np.float32)


def codificar(x: np.ndarray, formato: str, ffmpeg: str | None) -> tuple[bytes, str, str]:
    if formato == "ogg":
        r = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1",
                            "-i", "pipe:0", "-c:a", "libopus", "-b:a", "32k", "-f", "ogg", "pipe:1"],
                           input=x.tobytes(), capture_output=True)
        if r.returncode != 0:
            sys.exit(f"ffmpeg no ha podido codificar: {r.stderr.decode(errors='ignore')[:200]}")
        return r.stdout, "pregunta.ogg", "audio/ogg"
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return b.getvalue(), "pregunta.wav", "audio/wav"


# ---------------------------------------------------------------- servicio de voz

def transcribir(url: str, datos: bytes, nombre: str, tipo: str, modelo: str, prompt: str | None) -> str:
    limite = "----cidia" + uuid.uuid4().hex
    campos = {"model": modelo, "language": "es", "response_format": "json", "temperature": "0"}
    if prompt:
        campos["prompt"] = prompt
    cuerpo = b"".join(
        f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in campos.items())
    cuerpo += (f'--{limite}\r\nContent-Disposition: form-data; name="file"; filename="{nombre}"\r\n'
               f"Content-Type: {tipo}\r\n\r\n").encode() + datos + f"\r\n--{limite}--\r\n".encode()
    pet = urllib.request.Request(url.rstrip("/") + "/audio/transcriptions", data=cuerpo, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={limite}"})
    for intento in range(2):
        try:
            with urllib.request.urlopen(pet, timeout=300) as r:
                return json.loads(r.read().decode("utf-8")).get("text", "")
        except OSError as e:  # URLError, HTTPError, tiempo agotado o conexión cortada
            if intento:
                raise SystemExit(f"El servicio de voz no responde en {url}: {e}") from e
            time.sleep(3)
    return ""


def salud(url: str) -> dict:
    try:
        with urllib.request.urlopen(url.rstrip("/").removesuffix("/v1") + "/health", timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


# ---------------------------------------------------------------- informe

def resumir(filas: list[dict], prompt_texto: str) -> list[dict]:
    vocab = set(normalizar(prompt_texto))
    resumen = []
    claves = sorted({(f["nivel"], f["con_prompt"]) for f in filas},
                    key=lambda k: (k[1], -999 if k[0] == "limpio" else -float(k[0])))
    for nivel, con_prompt in claves:
        g = [f for f in filas if f["nivel"] == nivel and f["con_prompt"] == con_prompt]
        terminos = [(t, ok) for f in g for t, ok in f["terminos"].items()]
        dentro = [ok for t, ok in terminos if set(normalizar(t.split("|")[0])) <= vocab]
        fuera = [ok for t, ok in terminos if not set(normalizar(t.split("|")[0])) <= vocab]
        resumen.append({
            "nivel": nivel, "con_prompt": con_prompt, "frases": len(g),
            "wer": sum(f["err_palabras"] for f in g) / max(1, sum(f["n_palabras"] for f in g)),
            "cer": sum(f["err_caracteres"] for f in g) / max(1, sum(f["n_caracteres"] for f in g)),
            "terminos": sum(ok for _, ok in terminos) / max(1, len(terminos)),
            "terminos_vocab": sum(dentro) / max(1, len(dentro)), "n_vocab": len(dentro),
            "terminos_fuera": sum(fuera) / max(1, len(fuera)), "n_fuera": len(fuera),
            "exactas": sum(f["err_palabras"] == 0 for f in g),
            "tiempo_medio_s": sum(f["tiempo_s"] for f in g) / len(g),
            "rtf": sum(f["tiempo_s"] for f in g) / sum(f["duracion_s"] for f in g),
        })
    return resumen


def tabla_md(resultados: list[dict]) -> str:
    lineas = ["| Modelo | Prompt | SNR | WER | CER | Términos clave | En el vocabulario | Fuera | Frases exactas "
              "| Tiempo medio (s) | RTF |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for res in resultados:
        for r in res["resumen"]:
            snr = "limpio" if r["nivel"] == "limpio" else f'{r["nivel"]} dB'
            cifras = (f'{r["wer"]:.1%} | {r["cer"]:.1%} | {r["terminos"]:.0%} | {r["terminos_vocab"]:.0%} '
                      f'| {r["terminos_fuera"]:.0%} | {r["exactas"]}/{r["frases"]} | {r["tiempo_medio_s"]:.2f} '
                      f'| {r["rtf"]:.2f}').replace(".", ",")  # coma decimal
            lineas.append(f'| {res["modelo"]} | {"sí" if r["con_prompt"] else "no"} | {snr} | {cifras} |')
    return "\n".join(lineas)


def informe_md(res: dict) -> str:
    partes = [f'# Prueba de audio con ruido: modelo {res["modelo"]}', "",
              f'{res["fecha"]} · {res["url"]} · voz «{res["voz"]}» · formato {res["formato"]} · '
              f'{res["n_frases"]} frases · carga del modelo {res["carga_s"]:.1f} s', "", tabla_md([res]), "",
              "## Términos clave fallados", ""]
    for r in res["resumen"]:
        fallos = [(f["id"], t, f["hipotesis"]) for f in res["filas"]
                  if f["nivel"] == r["nivel"] and f["con_prompt"] == r["con_prompt"]
                  for t, ok in f["terminos"].items() if not ok]
        snr = "limpio" if r["nivel"] == "limpio" else f'{r["nivel"]} dB'
        partes.append(f'### {snr}, {"con" if r["con_prompt"] else "sin"} prompt ({len(fallos)})')
        partes += [f"* F{i:02d} «{t}»: {h or '(vacío)'}" for i, t, h in fallos] or ["* Ninguno."]
        partes.append("")
    return "\n".join(partes)


# ---------------------------------------------------------------- principal

def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:18721/v1", help="base del servicio de voz (…/v1)")
    ap.add_argument("--modelo", default=None, help="campo model y etiqueta (por defecto, el que diga /health)")
    ap.add_argument("--niveles", default="limpio,20,10,5,0", help="SNR en dB separadas por comas; «limpio» sin ruido")
    ap.add_argument("--frases", type=int, default=len(FRASES), help="cuántas frases usar (de las 20)")
    ap.add_argument("--prompt", choices=["no", "si", "ambos"], default="no", help="prompt inicial de vocabulario")
    ap.add_argument("--texto-prompt", default=PROMPT_PLANTA)
    ap.add_argument("--formato", choices=["ogg", "wav"], default="ogg", help="ogg = Opus 32 kbit/s, como el navegador")
    ap.add_argument("--semilla", type=int, default=2026)
    ap.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "cidia-prueba-ruido")
    ap.add_argument("--salida", type=Path, default=REPO / "servidor" / "asr" / "resultados")
    ap.add_argument("--guardar-audios", action="store_true", help="guarda las mezclas en la caché para escucharlas")
    ap.add_argument("--tabla", nargs="+", type=Path, metavar="JSON", help="solo une resultados en una tabla")
    a = ap.parse_args()

    if a.tabla:
        print(tabla_md([json.loads(p.read_text(encoding="utf-8")) for p in a.tabla]))
        return

    ffmpeg = buscar_ffmpeg() if a.formato == "ogg" else None
    if a.formato == "ogg" and not ffmpeg:
        print("Sin ffmpeg: se envía WAV.")
        a.formato = "wav"
    estado = salud(a.url)
    if "error" in estado:
        sys.exit(f"El servicio de voz no responde en {a.url}: {estado['error']}")
    modelo = a.modelo or estado.get("modelo", "whisper")
    niveles = [None if n.strip() == "limpio" else float(n) for n in a.niveles.split(",")]
    usos_prompt = {"no": [False], "si": [True], "ambos": [False, True]}[a.prompt]
    audios, voz = sintetizar(a.cache)
    frases = FRASES[: a.frases]
    print(f"Servicio {a.url} · modelo {modelo} · voz {voz} · {len(frases)} frases · niveles {a.niveles}")

    t0 = time.perf_counter()  # primera petición: carga el modelo, no cuenta
    transcribir(a.url, *codificar(mezclar(audios[0], np.zeros(SR * 30, np.float32), None), a.formato, ffmpeg),
                modelo, None)
    carga = time.perf_counter() - t0

    filas = []
    for con_prompt in usos_prompt:
        for snr in niveles:
            nivel = "limpio" if snr is None else f"{snr:g}"
            for i, ((ref, _, terminos), voz_i) in enumerate(zip(frases, audios, strict=False), 1):
                rng = np.random.default_rng(a.semilla + i)  # mismo ruido para una frase en todos los niveles
                x = mezclar(voz_i, ruido_industrial(len(voz_i) + 2 * int(PAUSA_S * SR) + SR, rng), snr)
                datos, nombre, tipo = codificar(x, a.formato, ffmpeg)
                if a.guardar_audios:
                    (a.cache / "mezclas").mkdir(exist_ok=True)
                    (a.cache / "mezclas" / f"F{i:02d}-{nivel}{Path(nombre).suffix}").write_bytes(datos)
                t = time.perf_counter()
                hip = transcribir(a.url, datos, nombre, tipo, modelo, a.texto_prompt if con_prompt else None)
                dt = time.perf_counter() - t
                nr, nh = normalizar(ref), normalizar(hip)
                filas.append({
                    "id": i, "nivel": nivel, "con_prompt": con_prompt, "referencia": ref, "hipotesis": hip,
                    "ref_normalizada": " ".join(nr), "hip_normalizada": " ".join(nh),
                    "err_palabras": levenshtein(nr, nh), "n_palabras": len(nr),
                    "err_caracteres": levenshtein(" ".join(nr), " ".join(nh)), "n_caracteres": len(" ".join(nr)),
                    "terminos": {tm: contiene(nh, tm) for tm in terminos},
                    "tiempo_s": round(dt, 3), "duracion_s": round(len(x) / SR, 3),
                })
            r = resumir([f for f in filas if f["nivel"] == nivel and f["con_prompt"] == con_prompt], a.texto_prompt)[0]
            print(f'  {"con" if con_prompt else "sin"} prompt, {nivel:>6}: WER {r["wer"]:.1%} · CER {r["cer"]:.1%} · '
                  f'términos {r["terminos"]:.0%} · {r["tiempo_medio_s"]:.2f} s/frase')

    res = {"fecha": datetime.now().isoformat(timespec="seconds"), "url": a.url, "modelo": modelo, "salud": estado,
           "voz": voz, "formato": a.formato, "semilla": a.semilla, "n_frases": len(frases), "niveles": a.niveles,
           "prompt": a.texto_prompt if True in usos_prompt else None, "carga_s": round(carga, 2),
           "resumen": resumir(filas, a.texto_prompt), "filas": filas}
    a.salida.mkdir(parents=True, exist_ok=True)
    base = a.salida / f"ruido-{modelo}-{datetime.now():%Y%m%d-%H%M}"
    base.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    base.with_suffix(".md").write_text(informe_md(res), encoding="utf-8")
    print(f"Resultados: {base.with_suffix('.json')} y .md")


if __name__ == "__main__":
    main()
