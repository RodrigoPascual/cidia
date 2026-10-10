"""Recorrido completo de la demostración de CidIA contra un gateway en marcha (modelos reales).

Sigue el guion de datos-demo/README.md por la API, como lo haría la interfaz, y mide cada paso:

  1. La experta sube el vídeo sintético de la brida B; CidIA genera el borrador de instrucción.
  2. La experta corrige el borrador (marca un paso crítico) y lo publica.
  3. Preguntas del cuestionario: aprueba las que propone el modelo (o escribe unas si no hay).
  4. El aprendiz hace la tarea en modo planta: pregunta por voz en un paso, confirma los
     críticos, envía la foto final y termina. Repite la tarea hasta tres veces (nivel L).
  5. Cuestionario aprobado.
  6. El jefe ve la ejecución y registra la observación en el puesto: el ILUO sube a U.
  7. El pasaporte del aprendiz lo refleja.
  8. Un operario aporta una solución por nota de voz, el jefe la valida y el copiloto la cita.

Cada ejecución crea sus propios datos con nombres únicos (tarea, instrucción, aportación), así
que se puede repetir. Por defecto trabaja en un departamento propio, «Pruebas QA», con cuentas
propias (qa.experta, qa.jefe, qa.aprendiz, qa.operario): no ensucia los datos de la demostración
que ven las demás personas. Con `--personas demo` usa las cuentas de la semilla (carmen, javier,
lucia y pedro).

Uso (desde servidor/gateway):
    .venv/Scripts/python qa/recorrido_demo.py --url http://127.0.0.1:18806 --env .env.qa
    .venv/Scripts/python qa/recorrido_demo.py --url http://servidor:8080 --personas demo

Contraseñas: la de `admin` sale de CIDIA_ADMIN_CONTRASENA o, si no está, de CIDIA_DEMO_CONTRASENA
(del entorno o del fichero indicado con --env). Nunca se imprimen. Con `--personas propias` la
administración restablece en cada ejecución la contraseña temporal de las cuentas de prueba.

Deja un resumen legible en la consola y un JSON en _registros_pruebas/ (o en --salida).
Código de salida 0 si todo ha ido bien, 1 si algún paso ha fallado.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

GATEWAY = Path(__file__).resolve().parents[1]
RAIZ = GATEWAY.parents[1]
VIDEO = RAIZ / "datos-demo" / "video" / "brida-b-sintetico.mp4"
AUDIO_APORTACION = GATEWAY / "cidia" / "semilla_datos" / "audio" / "aportacion-prensa3.ogg"
AUDIO_RESERVA = GATEWAY / "cidia" / "semilla_datos" / "audio" / "aportacion-juntas.ogg"

PREGUNTA_VOZ = "¿Qué llave tengo que usar para apretar los tornillos?"
PREGUNTA_COPILOTO = "La prensa 3 se ha atascado al cambiar el molde, ¿qué hago?"

DEP_QA = "Pruebas QA"
PUESTO_QA = "Banco de pruebas"
CUENTAS_QA = {
    # papel: (usuario, nombre, rol, es_experto, nivel)
    "experta": ("qa.experta", "Experta QA", "empleado", True, 2),
    "jefe": ("qa.jefe", "Jefe QA", "jefe", False, 3),
    "aprendiz": ("qa.aprendiz", "Aprendiz QA", "empleado", False, 1),
    "operario": ("qa.operario", "Operario QA", "empleado", False, 1),
}
CUENTAS_DEMO = {"experta": "carmen", "jefe": "javier", "aprendiz": "lucia", "operario": "pedro"}

# PNG de 1x1 píxel por si no hay imagen de referencia que reutilizar como foto.
PNG_MINIMO = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6364f8ffbf1e000502027f3d0c2bb20000000049454e44ae426082"
)

PS_VOZ = r"""
param([string]$Texto, [string]$Salida)
Add-Type -AssemblyName System.Speech
$voz = New-Object System.Speech.Synthesis.SpeechSynthesizer
$es = $voz.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'es-*' } | Select-Object -First 1
if (-not $es) { Write-Error 'No hay ninguna voz en castellano'; exit 2 }
$voz.SelectVoice($es.VoiceInfo.Name)
$formato = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$voz.SetOutputToWaveFile($Salida, $formato)
$voz.Speak($Texto)
$voz.SetOutputToNull()
"""


class FalloPaso(RuntimeError):
    """Un paso no ha dado el resultado esperado (el mensaje se muestra tal cual)."""


# --------------------------------------------------------------------------- registro de pasos


@dataclass
class Paso:
    nombre: str
    inicio: float
    segundos: float = 0.0
    ok: bool = False
    detalle: str = ""
    datos: dict[str, Any] = field(default_factory=dict)


class Informe:
    def __init__(self) -> None:
        self.pasos: list[Paso] = []
        self.inicio = time.perf_counter()

    @contextmanager
    def paso(self, nombre: str) -> Iterator[Paso]:
        p = Paso(nombre=nombre, inicio=time.perf_counter())
        self.pasos.append(p)
        print(f"· {nombre}...", flush=True)
        try:
            yield p
            p.ok = True
        except FalloPaso as e:
            p.detalle = str(e)
        except httpx.HTTPError as e:
            p.detalle = f"Error de red: {e}"
        except Exception as e:  # noqa: BLE001  (se apunta y se sigue con lo que no dependa de él)
            p.detalle = f"{type(e).__name__}: {e}"
            traceback.print_exc()
        finally:
            p.segundos = time.perf_counter() - p.inicio
            marca = "ok" if p.ok else "FALLO"
            texto = f"  {marca} en {p.segundos:.1f} s"
            if p.detalle:
                texto += f": {p.detalle}"
            print(texto, flush=True)

    def correcto(self, nombre: str) -> bool:
        return any(p.nombre == nombre and p.ok for p in self.pasos)

    def resumen(self) -> str:
        ancho = max((len(p.nombre) for p in self.pasos), default=10)
        lineas = ["", "Resumen del recorrido", "=" * (ancho + 28)]
        for p in self.pasos:
            lineas.append(f"{'ok   ' if p.ok else 'FALLO'}  {p.nombre.ljust(ancho)}  {p.segundos:8.1f} s")
            if p.detalle:
                lineas.append(f"       {p.detalle}")
        total = time.perf_counter() - self.inicio
        fallos = sum(1 for p in self.pasos if not p.ok)
        lineas.append("=" * (ancho + 28))
        lineas.append(f"{len(self.pasos)} pasos, {fallos} con fallo, {total:.0f} s en total.")
        return "\n".join(lineas)

    def a_dict(self) -> dict[str, Any]:
        return {
            "pasos": [{"nombre": p.nombre, "ok": p.ok, "segundos": round(p.segundos, 2), "detalle": p.detalle,
                       "datos": p.datos} for p in self.pasos],
            "total_segundos": round(time.perf_counter() - self.inicio, 1),
            "fallos": sum(1 for p in self.pasos if not p.ok),
        }


# --------------------------------------------------------------------------- cliente


class Cliente:
    """Llamadas a la API con el token de cada persona. Los errores HTTP se convierten en FalloPaso
    con el `detail` en castellano que devuelve el gateway."""

    def __init__(self, url: str, timeout: float) -> None:
        self.http = httpx.Client(base_url=url.rstrip("/"), timeout=httpx.Timeout(timeout, connect=15.0))
        self.tokens: dict[str, str] = {}

    def entrar(self, papel: str, usuario: str, contrasena: str) -> dict[str, Any]:
        r = self.http.post("/api/auth/login", json={"usuario": usuario, "contrasena": contrasena})
        if r.status_code != 200:
            raise FalloPaso(f"No se puede iniciar sesión como {usuario}: {self._detalle(r)}")
        datos = r.json()
        self.tokens[papel] = datos["token"]
        return datos["perfil"]

    def cab(self, papel: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[papel]}"}

    @staticmethod
    def _detalle(r: httpx.Response) -> str:
        try:
            d = r.json()
            return f"{r.status_code} {d.get('detail', d)}"
        except ValueError:
            return f"{r.status_code} {r.text[:200]}"

    def pedir(self, papel: str, metodo: str, ruta: str, esperado: tuple[int, ...] = (200,), **kw: Any) -> Any:
        r = self.http.request(metodo, ruta, headers=self.cab(papel), **kw)
        if r.status_code not in esperado:
            raise FalloPaso(f"{metodo} {ruta.split('?')[0]} → {self._detalle(r)}")
        if r.headers.get("content-type", "").startswith("application/json"):
            return r.json()
        return r.content

    def get(self, papel: str, ruta: str, **kw: Any) -> Any:
        return self.pedir(papel, "GET", ruta, **kw)

    def post(self, papel: str, ruta: str, **kw: Any) -> Any:
        return self.pedir(papel, "POST", ruta, **kw)

    def put(self, papel: str, ruta: str, **kw: Any) -> Any:
        return self.pedir(papel, "PUT", ruta, **kw)

    def sse(self, papel: str, ruta: str, cuerpo: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        """POST que responde con Server-Sent Events. Devuelve [(evento, datos)]."""
        eventos: list[tuple[str, dict[str, Any]]] = []
        with self.http.stream("POST", ruta, json=cuerpo, headers=self.cab(papel)) as r:
            if r.status_code != 200:
                r.read()
                raise FalloPaso(f"POST {ruta} → {self._detalle(r)}")
            evento, datos = "message", ""
            for linea in r.iter_lines():
                if linea.startswith("event:"):
                    evento = linea[6:].strip()
                elif linea.startswith("data:"):
                    datos += linea[5:].strip()
                elif not linea.strip() and datos:
                    eventos.append((evento, json.loads(datos)))
                    evento, datos = "message", ""
            if datos:
                eventos.append((evento, json.loads(datos)))
        return eventos


def esperar(descripcion: str, comprobar: Callable[[], Any], maximo: float, cada: float = 4.0,
            al_avanzar: Callable[[Any], None] | None = None) -> Any:
    """Repite `comprobar` hasta que devuelve algo verdadero o se agota el tiempo."""
    limite = time.monotonic() + maximo
    while True:
        valor = comprobar()
        if valor:
            return valor
        if al_avanzar is not None:
            al_avanzar(None)
        if time.monotonic() > limite:
            raise FalloPaso(f"Se ha agotado la espera ({maximo:.0f} s): {descripcion}")
        time.sleep(cada)


# --------------------------------------------------------------------------- utilidades


def leer_env(fichero: Path | None) -> dict[str, str]:
    datos: dict[str, str] = {}
    if fichero and fichero.exists():
        for linea in fichero.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.strip().startswith("#"):
                k, v = linea.split("=", 1)
                datos[k.strip()] = v.strip().strip('"').strip("'")
    return datos


def sintetizar_voz(texto: str, destino: Path) -> bool:
    """WAV con la voz en castellano de Windows. False si no hay síntesis disponible."""
    if os.name != "nt":
        return False
    script = destino.with_suffix(".ps1")
    script.write_text(PS_VOZ, encoding="utf-8-sig")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                            "-Texto", texto, "-Salida", str(destino)], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and destino.exists() and destino.stat().st_size > 1000


def citas(texto: str) -> set[int]:
    return {int(n) for n in re.findall(r"\[(\d{1,2})\]", texto or "")}


def recortar(texto: Any, n: int = 160) -> str:
    if isinstance(texto, dict):  # transcripción {texto, segmentos}
        texto = texto.get("texto")
    texto = re.sub(r"\s+", " ", texto if isinstance(texto, str) else "").strip()
    return texto if len(texto) <= n else texto[: n - 1] + "…"


# --------------------------------------------------------------------------- recorrido


class Recorrido:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.sufijo = datetime.now().strftime("%m%d-%H%M%S")
        self.c = Cliente(args.url, args.timeout)
        self.inf = Informe()
        env = {**leer_env(args.env), **{k: v for k, v in os.environ.items() if k.startswith("CIDIA_")}}
        self.contrasena_admin = env.get("CIDIA_ADMIN_CONTRASENA") or env.get("CIDIA_DEMO_CONTRASENA") or ""
        self.contrasena_demo = env.get("CIDIA_DEMO_CONTRASENA") or ""
        self.tmp = Path(tempfile.mkdtemp(prefix="cidia_recorrido_"))
        self.ids: dict[str, Any] = {"sufijo": self.sufijo, "personas": args.personas}
        self.perfiles: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------ preparación

    def preparar(self) -> None:
        with self.inf.paso("Servidor en marcha") as p:
            r = self.c.http.get("/salud")
            if r.status_code != 200:
                raise FalloPaso(f"/salud responde {r.status_code}")
            info = self.c.http.get("/api/sistema/info").json()
            p.datos = {"version": info.get("version"), "empresa": info.get("empresa")}
            p.detalle = f"CidIA {info.get('version')} · {info.get('empresa')}"

        with self.inf.paso("Sesión de administración"):
            if not self.contrasena_admin:
                raise FalloPaso("Falta CIDIA_ADMIN_CONTRASENA o CIDIA_DEMO_CONTRASENA (entorno o --env).")
            self.c.entrar("admin", self.args.admin, self.contrasena_admin)

        with self.inf.paso("Personas del recorrido") as p:
            if self.args.personas == "demo":
                if not self.contrasena_demo:
                    raise FalloPaso("Falta CIDIA_DEMO_CONTRASENA para las cuentas de la demostración.")
                for papel, usuario in CUENTAS_DEMO.items():
                    self.perfiles[papel] = self.c.entrar(papel, usuario, self.contrasena_demo)
                experta = self.c.get("admin", f"/api/admin/empleados/{self.perfiles['experta']['id']}")
                if not experta.get("puesto"):
                    raise FalloPaso("La experta de la demostración no tiene puesto.")
                self.ids["puesto_id"] = experta["puesto"]["id"]
            else:
                self._cuentas_propias()
            p.detalle = ", ".join(f"{papel}: {perf['usuario']}" for papel, perf in self.perfiles.items())
            p.datos = {papel: perf["usuario"] for papel, perf in self.perfiles.items()}

        with self.inf.paso("Tarea nueva para el recorrido") as p:
            t = self.c.post("admin", "/api/admin/tareas", json={
                "puesto_id": self.ids["puesto_id"], "codigo": f"QA-{self.sufijo}",
                "nombre": f"Montaje de la brida B (recorrido {self.sufijo})", "criticidad": 3, "nivel_minimo": 1,
                "riesgos_prl": "Atrapamiento de manos; proyección de partículas.",
            })
            self.ids["tarea_id"] = t["id"]
            p.detalle = f"{t.get('codigo')} · id {t['id']}"

    def _cuentas_propias(self) -> None:
        org = self.c.get("admin", "/api/admin/organizacion")
        dep = next((d for d in org["departamentos"] if d["nombre"] == DEP_QA), None)
        if dep is None:
            dep = self.c.post("admin", "/api/admin/departamentos", json={
                "nombre": DEP_QA, "codigo": "QAR", "descripcion": "Departamento del recorrido automático de pruebas."})
            dep["puestos"] = []
        puesto = next((x for x in dep.get("puestos", []) if x["nombre"] == PUESTO_QA), None)
        if puesto is None:
            puesto = self.c.post("admin", "/api/admin/puestos", json={"departamento_id": dep["id"], "nombre": PUESTO_QA})
        self.ids.update({"departamento_id": dep["id"], "puesto_id": puesto["id"]})
        niveles = {n["orden"]: n["id"] for n in self.c.get("admin", "/api/admin/niveles")}
        for papel, (usuario, nombre, rol, experto, nivel) in CUENTAS_QA.items():
            lista = self.c.get("admin", "/api/admin/empleados", params={"texto": usuario})["empleados"]
            emp = next((e for e in lista if e["usuario"] == usuario), None)
            datos = {"nombre": nombre, "departamento_id": dep["id"], "puesto_id": puesto["id"], "rol": rol,
                     "es_experto": experto, "nivel_id": niveles.get(nivel)}
            if emp is None:
                emp = self.c.post("admin", "/api/admin/empleados", json={"usuario": usuario, **datos})["empleado"]
            else:
                if not emp["activo"]:
                    self.c.post("admin", f"/api/admin/empleados/{emp['id']}/activar")
                self.c.put("admin", f"/api/admin/empleados/{emp['id']}", json=datos)
            temporal = self.c.post("admin", f"/api/admin/empleados/{emp['id']}/contrasena")["contrasena_temporal"]
            self.perfiles[papel] = self.c.entrar(papel, usuario, temporal)

    # ------------------------------------------------------------------ captura y publicación

    def captura(self) -> None:
        with self.inf.paso("Experta: sube el vídeo de la brida B") as p:
            if not self.args.video.exists():
                raise FalloPaso(f"No está el vídeo {self.args.video}")
            with self.args.video.open("rb") as f:
                cap = self.c.post("experta", "/api/captura/video",
                                  files={"fichero": (self.args.video.name, f, "video/mp4")},
                                  data={"tarea_id": str(self.ids["tarea_id"]),
                                        "titulo": f"Brida B · recorrido {self.sufijo}"})
            self.ids["captura_id"] = cap["id"]
            p.detalle = f"captura {cap['id']} · {self.args.video.stat().st_size // 1024} KB"

        with self.inf.paso("Procesado del vídeo hasta el borrador") as p:
            fases: dict[str, float] = {}
            t0 = time.perf_counter()

            def listo() -> dict[str, Any] | None:
                cap = self.c.get("experta", f"/api/captura/{self.ids['captura_id']}")
                fase = cap.get("fase_texto") or cap.get("fase") or "?"
                if fase not in fases:
                    fases[fase] = round(time.perf_counter() - t0, 1)
                    print(f"    {fases[fase]:6.1f} s  {fase} ({cap.get('progreso')} %)", flush=True)
                if cap["estado"] == "error":
                    raise FalloPaso(f"La captura ha fallado: {cap.get('mensaje')}")
                return cap if cap["estado"] == "borrador_listo" and cap.get("instruccion_id") else None

            cap = esperar("borrador de la captura", listo, self.args.espera, cada=5)
            self.ids["instruccion_id"] = cap["instruccion_id"]
            p.datos = {"fases_s": fases, "origen_borrador": cap.get("origen_borrador"),
                       "escenas": len(cap.get("escenas") or []), "transcripcion": recortar(cap.get("transcripcion"), 300)}
            p.detalle = f"instrucción {cap['instruccion_id']} · borrador por {cap.get('origen_borrador') or '?'}"

        with self.inf.paso("Experta: revisa y corrige el borrador") as p:
            ins = self.c.get("experta", f"/api/instrucciones/{self.ids['instruccion_id']}")
            pasos = ins.get("pasos") or []
            if not pasos:
                raise FalloPaso("El borrador no tiene pasos")
            # El paso del par de apriete (o el tercero) queda como crítico, como en el guion.
            critico = next((i for i, x in enumerate(pasos) if re.search(r"tornill|apriet|par\b|llave", (x.get("titulo") or "") + " " + (x.get("texto") or ""), re.I)), min(2, len(pasos) - 1))
            nuevos = []
            for i, x in enumerate(pasos):
                nuevos.append({"id": x["id"], "titulo": x.get("titulo") or f"Paso {i + 1}", "texto": x.get("texto"),
                               "es_critico": bool(x.get("es_critico")) or i == critico,
                               "es_seguridad": bool(x.get("es_seguridad")),
                               "criterio_aceptacion": x.get("criterio_aceptacion")
                               or ("Par de 25 N·m en los cuatro tornillos." if i == critico else None)})
            nuevos[0]["texto"] = (nuevos[0]["texto"] or "") + " Revisado por la experta."
            ins = self.c.put("experta", f"/api/instrucciones/{self.ids['instruccion_id']}", json={
                "titulo": f"Montaje de la brida B (recorrido {self.sufijo})", "pasos": nuevos})
            p.datos = {"pasos": len(ins["pasos"]), "criticos": ins.get("pasos_criticos"),
                       "titulos": [x["titulo"] for x in ins["pasos"]]}
            p.detalle = f"{len(ins['pasos'])} pasos, crítico el {critico + 1}"
            if len(ins["pasos"]) < 5:  # el vídeo narra 7 pasos («Paso 1…», «Paso 2»…)
                raise FalloPaso(f"El borrador del vídeo solo tiene {len(ins['pasos'])} pasos (el vídeo narra 7)")

        with self.inf.paso("Experta: publica la instrucción") as p:
            pub = self.c.post("experta", f"/api/instrucciones/{self.ids['instruccion_id']}/publicar")
            if pub.get("estado") != "publicada":
                raise FalloPaso(f"Estado tras publicar: {pub.get('estado')}")
            p.detalle = f"{pub.get('codigo')} v{pub.get('version')} · reevaluaciones: {pub.get('reevaluaciones')}"

    def instruccion_manual(self) -> None:
        """--sin-video: la experta escribe la instrucción a mano (recorrido rápido sin el vídeo)."""
        with self.inf.paso("Experta: escribe la instrucción a mano") as p:
            pasos = [
                {"titulo": "Preparar la brida y los tornillos", "texto": "Coloca la brida B y los 4 tornillos M8."},
                {"titulo": "Presentar la junta", "texto": "Centra la junta JT-80 sin pellizcarla."},
                {"titulo": "Apretar los tornillos en cruz", "texto": "Con la llave dinamométrica de 1/2\" a 25 N·m.",
                 "es_critico": True, "criterio_aceptacion": "Par de 25 N·m en los cuatro tornillos."},
                {"titulo": "Comprobar el montaje", "texto": "Revisa que la brida no tiene holgura."},
            ]
            ins = self.c.post("experta", "/api/instrucciones", json={
                "tarea_id": self.ids["tarea_id"], "titulo": f"Montaje de la brida B (recorrido {self.sufijo})",
                "resumen": "Montaje de la brida B en la línea 2.", "pasos": pasos})
            self.ids["instruccion_id"] = ins["id"]
            pub = self.c.post("experta", f"/api/instrucciones/{ins['id']}/publicar")
            p.detalle = f"{pub.get('codigo')} v{pub.get('version')} publicada"

    def preguntas(self) -> None:
        with self.inf.paso("Experta: aprueba las preguntas del cuestionario") as p:
            ruta = f"/api/evaluacion/preguntas?instruccion_id={self.ids['instruccion_id']}"
            t0 = time.perf_counter()

            def generadas() -> list[dict[str, Any]] | None:
                ps = self.c.get("experta", ruta)["preguntas"]
                return ps if any(x["estado"] == "propuesta" for x in ps) else None

            try:
                lista = esperar("preguntas propuestas por el modelo", generadas, self.args.espera_preguntas, cada=5)
            except FalloPaso:
                lista = self.c.get("experta", ruta)["preguntas"]
            espera = time.perf_counter() - t0
            aprobadas = []
            for x in [q for q in lista if q["estado"] == "propuesta"][:5]:
                try:
                    aprobadas.append(self.c.put("experta", f"/api/evaluacion/preguntas/{x['id']}",
                                                json={"estado": "aprobada"}))
                except FalloPaso as e:
                    print(f"    no se aprueba la pregunta {x['id']}: {e}")
            manuales = 0
            if len(aprobadas) < 2:  # el modelo pequeño no siempre propone preguntas válidas
                ins = self.c.get("experta", f"/api/instrucciones/{self.ids['instruccion_id']}")
                titulos = [x["titulo"] for x in ins["pasos"]]
                for i in range(min(3, len(titulos))):
                    otros = [t for t in titulos if t != titulos[i]][:2]
                    if len(otros) < 2:
                        break
                    self.c.post("experta", "/api/evaluacion/preguntas", json={
                        "instruccion_id": self.ids["instruccion_id"], "enunciado": f"¿Qué se hace en el paso {i + 1}?",
                        "opciones": [titulos[i], *otros], "correcta": 0,
                        "explicacion": f"El paso {i + 1} es «{titulos[i]}».", "paso_id": ins["pasos"][i]["id"]})
                    manuales += 1
            todas = self.c.get("experta", ruta)["preguntas"]
            self.ids["preguntas"] = {q["id"]: q["opciones"][q["correcta"]] for q in todas if q["estado"] == "aprobada"}
            if not self.ids["preguntas"]:
                raise FalloPaso("No hay ninguna pregunta aprobada")
            p.datos = {"propuestas_por_el_modelo": sum(1 for q in lista if q["estado"] == "propuesta"),
                       "aprobadas": len(aprobadas), "escritas_a_mano": manuales,
                       "espera_generacion_s": round(espera, 1)}
            p.detalle = (f"{len(aprobadas)} del modelo y {manuales} a mano "
                         f"(espera de la generación {espera:.0f} s)")

    # ------------------------------------------------------------------ modo planta

    def planta(self) -> None:
        tarea_id = self.ids["tarea_id"]
        with self.inf.paso("Aprendiz: abre la tarea en modo planta") as p:
            tareas = self.c.get("aprendiz", "/api/planta/tareas")
            mia = next((t for t in tareas if (t.get("id") or (t.get("tarea") or {}).get("id")) == tarea_id), None)
            if mia is None:
                raise FalloPaso(f"La tarea {tarea_id} no aparece en el modo planta del aprendiz ({len(tareas)} tareas)")
            ej = self.c.post("aprendiz", "/api/planta/ejecuciones", json={"tarea_id": tarea_id})
            self.ids["ejecucion_id"] = ej["id"]
            p.detalle = f"ejecución {ej['id']} · {ej['total_pasos']} pasos"

        with self.inf.paso("Aprendiz: pregunta por voz en el paso crítico") as p:
            ej = self.c.get("aprendiz", f"/api/planta/ejecuciones/{self.ids['ejecucion_id']}")
            critico = next((x for x in ej["pasos"] if x["es_critico"]), ej["pasos"][0])
            for x in ej["pasos"]:  # avanza hasta el paso crítico
                if x["id"] == critico["id"]:
                    break
                self.c.post("aprendiz", f"/api/planta/ejecuciones/{ej['id']}/pasos/{x['id']}/confirmar",
                            json={"critico_confirmado": x["es_critico"]})
            wav = self.tmp / "pregunta.wav"
            sintetizada = sintetizar_voz(PREGUNTA_VOZ, wav)
            audio = wav if sintetizada else AUDIO_RESERVA
            t0 = time.perf_counter()
            with audio.open("rb") as f:
                voz = self.c.post("aprendiz", "/api/voz/transcribir",
                                  files={"audio": (audio.name, f, "audio/wav" if sintetizada else "audio/ogg")})
            t_voz = time.perf_counter() - t0
            texto = (voz.get("texto") or "").strip() or PREGUNTA_VOZ
            t0 = time.perf_counter()
            eventos = self.c.sse("aprendiz", f"/api/planta/ejecuciones/{ej['id']}/preguntar",
                                 {"pregunta": texto, "paso_id": critico["id"]})
            t_resp = time.perf_counter() - t0
            tipos = [e for e, _ in eventos]
            if "error" in tipos:
                raise FalloPaso(f"El copiloto respondió con error: {next(d for e, d in eventos if e == 'error')}")
            respuesta = "".join(d.get("texto", "") for e, d in eventos if e == "token")
            fuentes = next((d.get("fuentes") for e, d in eventos if e == "fuentes"), []) or []
            fin = next((d for e, d in eventos if e == "fin"), {})
            if "fin" not in tipos:
                raise FalloPaso(f"La respuesta no terminó (eventos: {sorted(set(tipos))})")
            p.datos = {"voz_sintetizada": sintetizada, "transcripcion": texto, "transcribir_s": round(t_voz, 1),
                       "responder_s": round(t_resp, 1), "fuentes": [f.get("titulo") for f in fuentes],
                       "con_respaldo": fin.get("con_respaldo"), "respuesta": recortar(respuesta, 400)}
            p.detalle = (f"«{recortar(texto, 60)}» (voz {t_voz:.1f} s, respuesta {t_resp:.1f} s, "
                         f"{len(fuentes)} fuentes, respaldo: {fin.get('con_respaldo')})")
            self.ids["paso_critico"] = critico["id"]

        with self.inf.paso("Aprendiz: confirma los pasos y envía la foto") as p:
            ej = self.c.get("aprendiz", f"/api/planta/ejecuciones/{self.ids['ejecucion_id']}")
            self._confirmar_todo(ej)
            foto = self._foto(ej)
            t0 = time.perf_counter()
            v = self.c.post("aprendiz", f"/api/planta/ejecuciones/{ej['id']}/foto",
                            files={"imagen": ("resultado.png", foto, "image/png")})
            t_foto = time.perf_counter() - t0
            fin = self.c.post("aprendiz", f"/api/planta/ejecuciones/{ej['id']}/finalizar")
            if fin["estado"] != "completada":
                raise FalloPaso(f"La ejecución quedó «{fin['estado']}»")
            p.datos = {"veredicto_foto": {k: v.get(k) for k in ("estado", "coincide", "confianza", "comentario")},
                       "foto_s": round(t_foto, 1), "resumen": fin.get("resumen")}
            p.detalle = f"foto: {v.get('estado')} ({t_foto:.1f} s) · ejecución completada"

        with self.inf.paso("Aprendiz: repite la tarea dos veces más") as p:
            for _ in range(2):
                ej = self.c.post("aprendiz", "/api/planta/ejecuciones", json={"tarea_id": tarea_id})
                self._confirmar_todo(ej)
                fin = self.c.post("aprendiz", f"/api/planta/ejecuciones/{ej['id']}/finalizar")
                if fin["estado"] != "completada":
                    raise FalloPaso(f"La ejecución {ej['id']} quedó «{fin['estado']}»")
                self.ids["ultima_ejecucion_id"] = ej["id"]
            p.detalle = "3 ejecuciones completadas (la última sin consultas en los críticos)"

    def _confirmar_todo(self, ej: dict[str, Any]) -> None:
        for x in ej["pasos"]:
            if not x["confirmado"]:
                self.c.post("aprendiz", f"/api/planta/ejecuciones/{ej['id']}/pasos/{x['id']}/confirmar",
                            json={"critico_confirmado": x["es_critico"]})

    def _foto(self, ej: dict[str, Any]) -> bytes:
        """La imagen del último paso con imagen (como si la foto saliera igual que la del experto)."""
        for x in reversed(ej["pasos"]):
            if x.get("imagen_url"):
                r = self.c.http.get(x["imagen_url"])
                if r.status_code == 200 and r.content[:8] == PNG_MINIMO[:8]:
                    return r.content
        return PNG_MINIMO

    # ------------------------------------------------------------------ evaluación y progreso

    def evaluacion(self) -> None:
        tarea_id, aprendiz = self.ids["tarea_id"], self.perfiles["aprendiz"]["id"]
        with self.inf.paso("Aprendiz: responde el cuestionario") as p:
            cu = self.c.get("aprendiz", f"/api/evaluacion/cuestionario/{tarea_id}")
            if any("correcta" in q for q in cu["preguntas"]):
                raise FalloPaso("El cuestionario del aprendiz incluye la respuesta correcta")
            respuestas = {}
            for q in cu["preguntas"]:
                buena = self.ids["preguntas"].get(q["id"])
                opcion = next((o for o in q["opciones"] if o["texto"] == buena), q["opciones"][0])
                respuestas[str(q["id"])] = opcion["clave"]
            r = self.c.post("aprendiz", f"/api/evaluacion/cuestionario/{tarea_id}/responder",
                            json={"instruccion_id": cu["instruccion"]["id"], "respuestas": respuestas})
            if not r["aprobado"]:
                raise FalloPaso(f"Suspendido: {r['aciertos']} de {r['total']}")
            p.datos = {"aciertos": r["aciertos"], "total": r["total"], "nivel": r["nivel"]}
            p.detalle = f"{r['aciertos']}/{r['total']} · nivel {r['nivel']['letra'] or '-'}"

        with self.inf.paso("Jefe: revisa la ejecución y observa en el puesto") as p:
            ej = self.c.get("jefe", f"/api/planta/ejecuciones/{self.ids['ejecucion_id']}")
            consultas = ej.get("consultas")
            plantilla = self.c.get("jefe", "/api/evaluacion/observacion/plantilla",
                                   params={"usuario_id": aprendiz, "tarea_id": tarea_id})
            lista = [{"paso_id": x["paso_id"], "ok": True, "nota": None} for x in plantilla["lista"]]
            obs = self.c.post("jefe", "/api/evaluacion/observaciones", json={
                "usuario_id": aprendiz, "tarea_id": tarea_id, "instruccion_id": plantilla["instruccion"]["id"],
                "lista": lista, "aprobada": True, "comentario": f"Observación del recorrido {self.sufijo}: correcto."})
            p.datos = {"consultas_primera_ejecucion": consultas, "observacion": obs.get("nivel") or obs}
            p.detalle = f"{len(lista)} pasos comprobados · consultas en la 1.ª ejecución: {consultas}"

        with self.inf.paso("ILUO del aprendiz en la tarea") as p:
            det = self.c.get("jefe", f"/api/progreso/iluo/{aprendiz}/{tarea_id}")
            letra = det.get("letra") or (det.get("tarea") or {}).get("letra") or self._letra(det)
            p.datos = {"letra": letra}
            if letra != "U":
                raise FalloPaso(f"Se esperaba el nivel U y es «{letra or 'sin nivel'}»")
            p.detalle = "nivel U (sabe hacerlo sin ayuda)"

        with self.inf.paso("Pasaporte del aprendiz") as p:
            yo = self.c.get("aprendiz", "/api/progreso/yo")
            fila = next((t for t in yo["tareas"] if t["tarea"]["id"] == tarea_id), None)
            if fila is None:
                raise FalloPaso("La tarea no aparece en el pasaporte")
            if fila["letra"] != "U":
                raise FalloPaso(f"El pasaporte muestra «{fila['letra'] or 'sin nivel'}» y no U")
            p.detalle = f"{fila['tarea']['codigo']}: {fila['letra']} · {fila['nombre_nivel']}"

        with self.inf.paso("Jefe: matriz ILUO del equipo") as p:
            eq = self.c.get("jefe", "/api/progreso/equipo")
            texto = json.dumps(eq, ensure_ascii=False)
            if self.perfiles["aprendiz"]["nombre"] not in texto:
                raise FalloPaso("El aprendiz no aparece en la matriz del equipo")
            p.detalle = "el aprendiz aparece en la matriz"

    @staticmethod
    def _letra(det: dict[str, Any]) -> str:
        for clave in ("nivel", "detalle"):
            v = det.get(clave)
            if isinstance(v, dict) and v.get("letra") is not None:
                return v["letra"]
        return ""

    # ------------------------------------------------------------------ aportaciones

    def aportacion(self) -> None:
        with self.inf.paso("Operario: aporta una solución por voz") as p:
            audio = self.args.audio_aportacion
            with audio.open("rb") as f:
                ap = self.c.post("operario", "/api/aportaciones",
                                 files={"audio": (audio.name, f, "audio/ogg")}, data={"duracion": "20"})
            self.ids["aportacion_id"] = ap["id"]
            t0 = time.perf_counter()

            def procesada() -> dict[str, Any] | None:
                a = self.c.get("operario", f"/api/aportaciones/{self.ids['aportacion_id']}")
                return a if a["estado"] != "procesando" else None

            ap = esperar("transcripción y ordenación de la aportación", procesada, self.args.espera, cada=4)
            p.datos = {"procesado_s": round(time.perf_counter() - t0, 1), "estado": ap["estado"],
                       "transcripcion": recortar(ap.get("transcripcion"), 300), "titulo": ap.get("titulo"),
                       "problema": recortar(ap.get("problema")), "solucion": recortar(ap.get("solucion"))}
            if ap["estado"] != "pendiente":
                raise FalloPaso(f"La aportación quedó «{ap['estado']}»")
            p.detalle = f"«{recortar(ap.get('titulo'), 70)}» (procesada en {p.datos['procesado_s']} s)"

        with self.inf.paso("Jefe: valida la aportación") as p:
            pendientes = self.c.get("jefe", "/api/aportaciones/pendientes")["aportaciones"]
            if not any(a["id"] == self.ids["aportacion_id"] for a in pendientes):
                raise FalloPaso("La aportación no está en la bandeja del jefe")
            ap = next(a for a in pendientes if a["id"] == self.ids["aportacion_id"])
            sugerido = ap.get("nivel_minimo")
            titulo = f"Atasco en la prensa 3 al cambiar el molde: limpiar el sensor S4 (recorrido {self.sufijo})"
            # El jefe revisa el nivel: una solución de un operario la tiene que poder ver él mismo
            # (si el modelo sugiere un nivel mayor que el suyo, ni su autor la encontraría).
            nivel_autor = 1  # qa.operario y pedro son de nivel 1 (Operario)
            r = self.c.post("jefe", f"/api/aportaciones/{self.ids['aportacion_id']}/validar",
                            json={"titulo": titulo, "nivel_minimo": nivel_autor})
            self.ids["documento_id"] = r["documento"]["id"]
            t0 = time.perf_counter()

            def indexado() -> dict[str, Any] | None:
                d = self.c.get("jefe", f"/api/documentos/{self.ids['documento_id']}?fragmentos=0")
                if d["estado"] == "error":
                    raise FalloPaso(f"El indexado de la pregunta frecuente ha fallado: {d.get('mensaje_estado')}")
                return d if d["estado"] == "listo" and not d.get("indexando") else None

            esperar("indexado de la pregunta frecuente", indexado, self.args.espera, cada=3)
            p.datos = {"indexado_s": round(time.perf_counter() - t0, 1), "documento_id": self.ids["documento_id"],
                       "nivel_sugerido_por_el_modelo": sugerido, "nivel_validado": nivel_autor}
            p.detalle = f"publicada como pregunta frecuente (documento {self.ids['documento_id']}, " \
                        f"indexada en {p.datos['indexado_s']} s)"
            if isinstance(sugerido, int) and sugerido > nivel_autor:
                p.detalle += f"; aviso: el modelo sugería nivel {sugerido}, mayor que el de su autor"

        with self.inf.paso("Copiloto: cita la solución validada") as p:
            t0 = time.perf_counter()
            r = self.c.post("operario", "/api/consulta/simple", json={"pregunta": PREGUNTA_COPILOTO})
            t_resp = time.perf_counter() - t0
            fuentes = r.get("fuentes") or []
            numeros = [f.get("n") for f in fuentes if f.get("documento_id") == self.ids["documento_id"]]
            citadas = citas(r.get("respuesta") or "")
            p.datos = {"responder_s": round(t_resp, 1), "fuentes": [f.get("titulo") for f in fuentes],
                       "con_respaldo": r.get("con_respaldo"), "citas_en_respuesta": sorted(citadas),
                       "respuesta": recortar(r.get("respuesta"), 400)}
            if not numeros:
                raise FalloPaso("La solución validada no está entre las fuentes de la respuesta")
            p.detalle = (f"fuente [{numeros[0]}] en {t_resp:.1f} s; "
                         + ("citada en el texto" if set(numeros) & citadas else "el modelo no la cita con [n]"))
            p.datos["citada_en_texto"] = bool(set(numeros) & citadas)

    # ------------------------------------------------------------------ limpieza

    def limpiar(self) -> None:
        """Con cuentas propias, la pregunta frecuente se borra al final para que la siguiente
        ejecución compruebe la cita de SU aportación y no la de una anterior."""
        if self.args.personas != "propias" or self.args.conservar or "documento_id" not in self.ids:
            return
        with self.inf.paso("Limpieza: retira la pregunta frecuente del recorrido"):
            self.c.pedir("jefe", "DELETE", f"/api/documentos/{self.ids['documento_id']}")

    # ------------------------------------------------------------------ ejecución

    def ejecutar(self) -> int:
        print(f"Recorrido de la demostración contra {self.args.url} (sufijo {self.sufijo})\n", flush=True)
        self.preparar()
        if self.inf.correcto("Tarea nueva para el recorrido"):
            if self.args.sin_video:
                self.instruccion_manual()
                listo = self.inf.correcto("Experta: escribe la instrucción a mano")
            else:
                self.captura()
                listo = self.inf.correcto("Experta: publica la instrucción")
            if listo:
                self.preguntas()
                self.planta()
                if self.inf.correcto("Aprendiz: repite la tarea dos veces más") and \
                        self.inf.correcto("Experta: aprueba las preguntas del cuestionario"):
                    self.evaluacion()
            if all(p in self.perfiles for p in ("operario", "jefe")):
                self.aportacion()
            self.limpiar()
        print(self.inf.resumen())
        salida = self.args.salida or (GATEWAY / "_registros_pruebas" / f"recorrido_demo_{self.sufijo}.json")
        salida.parent.mkdir(parents=True, exist_ok=True)
        salida.write_text(json.dumps({"url": self.args.url, "ids": self.ids, **self.inf.a_dict()},
                                     ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\nDetalle en {salida}")
        return 1 if any(not p.ok for p in self.inf.pasos) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Recorrido completo de la demostración de CidIA por la API.")
    ap.add_argument("--url", default="http://127.0.0.1:8080", help="Dirección del gateway")
    ap.add_argument("--env", type=Path, default=None, help="Fichero .env del que leer las contraseñas")
    ap.add_argument("--personas", choices=("propias", "demo"), default="propias",
                    help="propias: departamento y cuentas de prueba; demo: carmen, javier, lucia y pedro")
    ap.add_argument("--admin", default="admin", help="Usuario de administración")
    ap.add_argument("--video", type=Path, default=VIDEO)
    ap.add_argument("--audio-aportacion", type=Path, default=AUDIO_APORTACION)
    ap.add_argument("--sin-video", action="store_true", help="La instrucción se escribe a mano (más rápido)")
    ap.add_argument("--espera", type=float, default=1500, help="Espera máxima de cada proceso largo (s)")
    ap.add_argument("--espera-preguntas", type=float, default=240, help="Espera máxima de las preguntas (s)")
    ap.add_argument("--timeout", type=float, default=600, help="Tiempo máximo de cada petición (s)")
    ap.add_argument("--conservar", action="store_true", help="No borra la pregunta frecuente al terminar")
    ap.add_argument("--salida", type=Path, default=None, help="Fichero JSON del resumen")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    return Recorrido(args).ejecutar()


if __name__ == "__main__":
    sys.exit(main())
