#!/usr/bin/env python3
"""Primera configuración de WeKnora v0.8.2 para CidIA.

Con WeKnora recién levantado (perfil «weknora» del despliegue), este script:

  1. espera a que WeKnora responda en /health;
  2. registra el administrador técnico (si aún no existe) e inicia sesión con él;
  3. crea la API key «cidia-gateway» con acceso completo y la escribe en el fichero que indique
     el operador, con permisos 600 (la clave NUNCA se imprime); si ese fichero ya tiene una
     clave válida, la reutiliza;
  4. comprueba que los modelos ya están en Ollama, los da de alta (chat y embeddings) y espera a
     que estén activos;
  5. ajusta cuántos resultados devuelve cada búsqueda (rerank_top_k del espacio);
  6. crea la base «Público» y una base por departamento con sus etiquetas (n1…n4, formacion y
     publico) y guarda sus ids en la base de datos de CidIA (salvo con --sin-bd);
  7. opcionalmente (--reindexar), vuelve a indexar en WeKnora los documentos que ya existían.

Uso (desde servidor/gateway, para que se lea su .env con la conexión a la BD de CidIA):

    .venv/bin/python ../weknora/inicializar.py \\
        --url http://127.0.0.1:18702/api/v1 \\
        --contrasena-fichero /ruta/segura/weknora_admin.txt \\
        --salida-clave /ruta/segura/cidia.env --formato env

La contraseña del administrador se lee de --contrasena-fichero, de la variable
WEKNORA_ADMIN_CONTRASENA o se pide por teclado. Ver README.md.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

RAIZ_GATEWAY = Path(__file__).resolve().parents[1] / "gateway"
NOMBRE_VARIABLE = "CIDIA_WEKNORA_API_KEY"


class Fallo(RuntimeError):
    """Error que se muestra al operador y termina el script."""


def paso(texto: str) -> None:
    print(f"· {texto}", flush=True)


def _mensaje(r: httpx.Response) -> str:
    try:
        datos = r.json()
    except ValueError:
        return r.text[:200] or f"estado {r.status_code}"
    err = datos.get("error") if isinstance(datos, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err)
    return str(err or (datos.get("message") if isinstance(datos, dict) else "") or f"estado {r.status_code}")


# --------------------------------------------------------------------------- pasos


def esperar_salud(raiz: str, segundos: int) -> None:
    limite = time.monotonic() + segundos
    while True:
        try:
            if httpx.get(f"{raiz}/health", timeout=5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        if time.monotonic() > limite:
            raise Fallo(f"WeKnora no responde en {raiz}/health tras {segundos} s. ¿Está levantado el perfil weknora?")
        time.sleep(3)


def iniciar_sesion(http: httpx.Client, usuario: str, email: str, contrasena: str) -> tuple[str, int]:
    """Registra al administrador (si hace falta) e inicia sesión. Devuelve (JWT, id del espacio)."""
    r = http.post("/auth/register", json={"username": usuario, "email": email, "password": contrasena})
    if r.status_code in (200, 201):
        paso(f"Administrador «{usuario}» registrado.")
    else:
        paso(f"No se registra el administrador ({_mensaje(r)}); se intenta iniciar sesión con él.")
    r = http.post("/auth/login", json={"email": email, "password": contrasena})
    if r.status_code != 200:
        raise Fallo(f"No se puede iniciar sesión en WeKnora con {email}: {_mensaje(r)}")
    datos = r.json()
    cuerpo = datos.get("data") if isinstance(datos.get("data"), dict) else datos
    token = cuerpo.get("token")
    espacio = (cuerpo.get("active_tenant") or {}).get("id") or (cuerpo.get("user") or {}).get("tenant_id")
    if not token or not espacio:
        raise Fallo("La respuesta del inicio de sesión de WeKnora no trae el token o el espacio.")
    paso(f"Sesión iniciada en el espacio {espacio}.")
    return str(token), int(espacio)


def leer_clave(ruta: Path) -> str | None:
    """Clave ya guardada en el fichero de salida (formato «clave» o «env»)."""
    if not ruta.is_file():
        return None
    texto = ruta.read_text(encoding="utf-8")
    m = re.search(rf"^{NOMBRE_VARIABLE}=(\S+)\s*$", texto, re.M)
    if m:
        return m.group(1)
    linea = texto.strip()
    return linea if linea.startswith("sk-") and "\n" not in linea else None


def clave_valida(url: str, clave: str) -> bool:
    try:
        r = httpx.get(f"{url}/knowledge-bases", headers={"X-API-Key": clave}, timeout=15)
    except httpx.HTTPError:
        return False
    return r.status_code == 200


def crear_clave(http: httpx.Client, jwt: str, espacio: int, nombre: str) -> str:
    # Solo se puede con el JWT del propietario del espacio (no con otra API key).
    r = http.post(f"/tenants/{espacio}/api-keys", headers={"Authorization": f"Bearer {jwt}"},
                  json={"name": nombre, "full_access": True})
    if r.status_code not in (200, 201):
        raise Fallo(f"No se ha podido crear la API key del gateway: {_mensaje(r)}")
    datos = r.json().get("data") or {}
    clave = datos.get("api_key") or datos.get("token")
    if not clave:
        raise Fallo("WeKnora no ha devuelto la API key creada.")
    return str(clave)


def guardar_clave(ruta: Path, clave: str, formato: str) -> None:
    """Escribe la clave con permisos 600. En formato env sustituye o añade la variable.

    Se escribe en un temporal y se renombra: si el fichero es el de secretos del despliegue, un
    corte a mitad no lo deja a medias.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if formato == "env":
        lineas = ruta.read_text(encoding="utf-8").splitlines() if ruta.is_file() else []
        lineas = [ln for ln in lineas if not ln.startswith(f"{NOMBRE_VARIABLE}=")]
        lineas.append(f"{NOMBRE_VARIABLE}={clave}")
        contenido = "\n".join(lineas) + "\n"
    else:
        contenido = clave + "\n"
    temporal = ruta.with_name(f".{ruta.name}.tmp")
    descriptor = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as f:
        f.write(contenido)
    try:
        os.chmod(temporal, 0o600)
    except OSError:
        pass
    os.replace(temporal, ruta)


def _modelos(http: httpx.Client) -> list[dict[str, Any]]:
    r = http.get("/models")
    if r.status_code != 200:
        raise Fallo(f"No se pueden listar los modelos de WeKnora: {_mensaje(r)}")
    return [m for m in r.json().get("data") or [] if isinstance(m, dict)]


def modelos_en_ollama(http: httpx.Client) -> set[str] | None:
    """Modelos que ya están en el Ollama de WeKnora (None si WeKnora no sabe decirlo)."""
    try:
        r = http.get("/initialization/ollama/models")
        lista = (r.json().get("data") or {}).get("models") if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError, AttributeError):
        return None
    if not isinstance(lista, list):
        return None
    return {str(m["name"]) for m in lista if isinstance(m, dict) and m.get("name")}


def asegurar_modelo(http: httpx.Client, cuerpo: dict[str, Any], espera: int,
                    presentes: set[str] | None = None, permitir_descarga: bool = False,
                    intervalo: float = 5) -> str:
    """Da de alta un modelo si no existe (mismo nombre y tipo) y espera a que esté activo."""
    nombre = cuerpo["name"]
    existente = next((m for m in _modelos(http) if m.get("name") == nombre and m.get("type") == cuerpo["type"]), None)
    if existente:
        mid = str(existente["id"])
        paso(f"Modelo {cuerpo['type']} «{nombre}» ya dado de alta.")
    else:
        # Con OLLAMA_OPTIONAL=true, un modelo que no está en Ollama queda «activo» sin existir, y si
        # Ollama no tiene salida a Internet tampoco se puede descargar: mejor avisar antes.
        if (cuerpo.get("source") == "local" and presentes is not None and not permitir_descarga
                and nombre not in presentes and f"{nombre}:latest" not in presentes):
            raise Fallo(f"El modelo «{nombre}» no está en Ollama. Descárgalo antes (ollama pull {nombre}) "
                        "o vuelve a ejecutar con --permitir-descarga.")
        r = http.post("/models", json=cuerpo)
        if r.status_code not in (200, 201):
            raise Fallo(f"No se ha podido dar de alta el modelo «{nombre}»: {_mensaje(r)}")
        mid = str(r.json()["data"]["id"])
        paso(f"Modelo {cuerpo['type']} «{nombre}» dado de alta.")
    # «source: local» puede lanzar una descarga en Ollama: hasta que no esté activo no se usa.
    # El estado se lee de la lista: GET /models/{id} responde 500 mientras se descarga (informe 03, §2.3).
    limite = time.monotonic() + espera
    while True:
        modelo = next((m for m in _modelos(http) if str(m.get("id")) == mid), None)
        if modelo is None:
            raise Fallo(f"El modelo «{nombre}» ya no aparece en WeKnora.")
        estado = str(modelo.get("status") or "active")
        if estado == "active":
            return mid
        if estado in ("failed", "error", "download_failed"):
            raise Fallo(f"El modelo «{nombre}» ha quedado en estado {estado}. Revisa Ollama.")
        if time.monotonic() > limite:
            raise Fallo(f"El modelo «{nombre}» sigue en estado {estado} tras {espera} s.")
        time.sleep(intervalo)


def ajustar_recuperacion(http: httpx.Client, top_k: int) -> None:
    r = http.get("/tenants/kv/retrieval-config")
    if r.status_code != 200:
        paso(f"Aviso: no se ha podido leer la configuración de búsqueda ({_mensaje(r)}).")
        return
    config = r.json().get("data") or {}
    config["rerank_top_k"] = top_k
    r = http.put("/tenants/kv/retrieval-config", json=config)
    if r.status_code != 200:
        paso(f"Aviso: no se ha podido ajustar rerank_top_k ({_mensaje(r)}).")
    else:
        paso(f"Cada búsqueda devolverá hasta {top_k} fragmentos.")


def preparar_bases(url: str, clave: str, modelo_embeddings: str, reindexar: bool) -> None:
    """Bases y etiquetas con los departamentos de CidIA; ids guardados en su BD."""
    sys.path.insert(0, str(RAIZ_GATEWAY))
    from cidia.conocimiento.weknora import MotorWeKnora
    from cidia.db import sesion_bd
    from cidia.modelos import Documento
    from sqlalchemy import select

    m = MotorWeKnora(url=url, api_key=clave)
    with sesion_bd() as bd:
        salida = m.preparar_bases(bd, modelo_embeddings_id=modelo_embeddings)
    paso(f"Base «Público» lista ({salida['publico']}).")
    for nombre, kb in salida["departamentos"].items():
        paso(f"Base «{nombre}» lista ({kb}).")
    if not reindexar:
        return
    from cidia.rutas.documentos import _partes_guardadas
    from cidia.servicios import documentos

    documentos.motor = lambda: m  # type: ignore[assignment]  # este proceso indexa con la clave recién creada
    with sesion_bd() as bd:
        ids = bd.scalars(select(Documento.id).where(Documento.estado.in_(["listo", "error"]))
                         .order_by(Documento.id)).all()
    paso(f"Reindexando {len(ids)} documentos en WeKnora…")
    for i, did in enumerate(ids, start=1):
        with sesion_bd() as bd:
            d = bd.get(Documento, did)
            if d is None:
                continue
            partes = None if d.ruta_fichero else _partes_guardadas(bd, d)
            documentos.indexar(bd, d, partes=partes)
            paso(f"[{i}/{len(ids)}] {d.titulo}: {d.estado}"
                 + (f" ({d.fragmentos_n} fragmentos)" if d.estado == "listo" else f" · {d.mensaje_estado}"))


# --------------------------------------------------------------------------- principal


def argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Primera configuración de WeKnora para CidIA.")
    p.add_argument("--url", default=os.environ.get("WEKNORA_URL", "http://127.0.0.1:18702/api/v1"),
                   help="Base de la API de WeKnora (…/api/v1).")
    p.add_argument("--usuario", default="admin", help="Usuario del administrador técnico de WeKnora.")
    p.add_argument("--email", default="admin@cidia.example", help="Correo con el que inicia sesión ese administrador.")
    p.add_argument("--contrasena-fichero", type=Path, help="Fichero con la contraseña del administrador.")
    p.add_argument("--salida-clave", type=Path, required=True, help="Fichero donde se escribe la API key del gateway.")
    p.add_argument("--formato", choices=["env", "clave"], default="env",
                   help=f"env: línea {NOMBRE_VARIABLE}=… (se sustituye si ya estaba); clave: solo la clave.")
    p.add_argument("--nombre-clave", default="cidia-gateway")
    p.add_argument("--modelo-chat", default=os.environ.get("CIDIA_LLM_MODELO_CHAT", "qwen3:0.6b"))
    p.add_argument("--modelo-embeddings", default=os.environ.get("CIDIA_LLM_MODELO_EMBEDDINGS", "qwen3-embedding:0.6b"))
    p.add_argument("--dimension", type=int, default=1024, help="Dimensión del modelo de embeddings (Qwen3-Embedding-0.6B: 1024).")
    p.add_argument("--contexto", type=int, default=8192, help="Ventana de contexto del modelo de chat.")
    p.add_argument("--top-k", type=int, default=20, help="Fragmentos que devuelve cada búsqueda (rerank_top_k).")
    p.add_argument("--espera", type=int, default=600, help="Segundos de espera para WeKnora y los modelos.")
    p.add_argument("--permitir-descarga", action="store_true",
                   help="Dar de alta modelos que aún no están en Ollama (WeKnora intentará descargarlos).")
    p.add_argument("--sin-bd", action="store_true", help="No crear bases ni tocar la BD de CidIA (las crea el gateway al subir).")
    p.add_argument("--reindexar", action="store_true", help="Volver a indexar en WeKnora los documentos existentes.")
    return p.parse_args()


def contrasena(args: argparse.Namespace) -> str:
    if args.contrasena_fichero:
        valor = args.contrasena_fichero.read_text(encoding="utf-8").strip()
    else:
        valor = os.environ.get("WEKNORA_ADMIN_CONTRASENA", "")
        if not valor and sys.stdin.isatty():
            valor = getpass.getpass("Contraseña del administrador de WeKnora: ")
    if len(valor) < 8:
        raise Fallo("Hace falta una contraseña de al menos 8 caracteres para el administrador de WeKnora.")
    return valor


def main() -> int:
    args = argumentos()
    url = args.url.rstrip("/")
    raiz = re.sub(r"/api/v\d+$", "", url)
    try:
        clave_admin = contrasena(args)
        paso(f"Esperando a WeKnora en {raiz}…")
        esperar_salud(raiz, args.espera)
        with httpx.Client(base_url=url, timeout=60, headers={"Accept-Language": "es-ES"}) as http:
            clave = leer_clave(args.salida_clave)
            if clave and clave_valida(url, clave):
                paso(f"Se reutiliza la API key que ya había en {args.salida_clave}.")
            else:
                jwt, espacio = iniciar_sesion(http, args.usuario, args.email, clave_admin)
                clave = crear_clave(http, jwt, espacio, args.nombre_clave)
                guardar_clave(args.salida_clave, clave, args.formato)
                paso(f"API key del gateway guardada en {args.salida_clave} (permisos 600).")
            http.headers["X-API-Key"] = clave
            presentes = modelos_en_ollama(http)
            if presentes is None:
                paso("Aviso: WeKnora no puede listar los modelos de Ollama; no se comprueba que existan.")
            asegurar_modelo(http, {
                "name": args.modelo_chat, "display_name": args.modelo_chat, "type": "KnowledgeQA", "source": "local",
                "description": "Modelo de chat de CidIA (Ollama)", "parameters": {"context_window": args.contexto},
            }, args.espera, presentes, args.permitir_descarga)
            emb = asegurar_modelo(http, {
                "name": args.modelo_embeddings, "display_name": args.modelo_embeddings, "type": "Embedding",
                "source": "local", "description": "Embeddings de CidIA (Ollama)",
                "parameters": {"embedding_parameters": {"dimension": args.dimension, "truncate_prompt_tokens": 2048}},
            }, args.espera, presentes, args.permitir_descarga)
            ajustar_recuperacion(http, args.top_k)
        if args.sin_bd:
            paso("Sin BD: las bases se crearán al subir el primer documento de cada departamento.")
        else:
            preparar_bases(url, clave, emb, args.reindexar)
    except RuntimeError as e:  # Fallo del script o ErrorWeKnora del gateway: el mensaje ya es legible
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    paso("WeKnora listo para CidIA. Siguiente paso: cerrar el registro (DISABLE_REGISTRATION=true) "
         "y arrancar el gateway con CIDIA_MOTOR_CONOCIMIENTO=weknora.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
