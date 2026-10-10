"""Evaluación: preguntas generadas desde los pasos, revisión del experto, cuestionarios y
observaciones en el puesto.

* Las preguntas se generan con el LLM a partir de los pasos de una instrucción (sobre todo
  los críticos) y quedan «propuestas» hasta que un experto las aprueba. Si el modelo falla o
  devuelve poco, se completan con preguntas sencillas construidas desde los pasos.
* El cuestionario solo usa preguntas aprobadas de la instrucción vigente y se corrige en el
  servidor (la respuesta correcta nunca viaja antes de responder).
* La observación la hace el jefe con la lista de comprobación de todos los pasos.
Cada evidencia nueva recalcula el nivel ILUO.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import random
import re
import unicodedata
from typing import Any

from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, contains_eager

from cidia import trabajos
from cidia.config import ajustes
from cidia.ia import llm
from cidia.modelos import (
    Instruccion,
    IntentoEval,
    NivelIluo,
    Observacion,
    Paso,
    PreguntaEval,
    Puesto,
    Tarea,
    Trabajo,
    Usuario,
)
from cidia.seguridad import Actor
from cidia.servicios import iluo
from cidia.xapi import registrar

log = logging.getLogger("cidia.evaluacion")

ESTADOS_PREGUNTA = ("propuesta", "aprobada", "descartada")
TIPO_TRABAJO = "generar_preguntas"

SISTEMA_PREGUNTAS = (
    "Eres un formador de una planta industrial. Redactas preguntas tipo test, en castellano claro, "
    "para comprobar que un operario ha entendido una instrucción de trabajo. Reglas:\n"
    "- Cada pregunta trata de un paso concreto; prioriza los pasos CRÍTICOS y de seguridad.\n"
    "- 3 o 4 opciones por pregunta, solo una correcta, todas plausibles y de longitud parecida.\n"
    "- Nada de «todas las anteriores» ni «ninguna de las anteriores».\n"
    "- Usa solo la información de la instrucción; no inventes datos.\n"
    "- La explicación dice por qué la respuesta correcta lo es, en una o dos frases.\n"
    "Responde SOLO con JSON con esta forma:\n"
    '{"preguntas": [{"enunciado": "...", "opciones": ["...", "...", "..."], "correcta": 0, '
    '"explicacion": "...", "paso": 2}]}\n'
    "«correcta» es la posición (empezando en 0) de la opción correcta y «paso» el número del paso."
)


# --------------------------------------------------------------------------- utilidades


def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\W+", " ", t).strip()


def _recortar(texto: str | None, n: int) -> str:
    t = re.sub(r"\s+", " ", texto or "").strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def departamento_de_instruccion(ins: Instruccion) -> int | None:
    return iluo.departamento_de_tarea(ins.tarea) if ins.tarea else None


def puede_revisar(actor: Actor, ins: Instruccion) -> bool:
    """Expertos (y jefes) del departamento de la instrucción, o la administración."""
    if actor.es_admin:
        return True
    return actor.es_experto and actor.departamento_id is not None \
        and departamento_de_instruccion(ins) == actor.departamento_id


def instruccion_para_revisar(bd: Session, actor: Actor, instruccion_id: int) -> Instruccion:
    ins = bd.get(Instruccion, instruccion_id)
    if ins is None:
        raise HTTPException(404, "No existe esa instrucción.")
    if not puede_revisar(actor, ins):
        raise HTTPException(403, "Solo los expertos del departamento de la instrucción pueden revisar sus preguntas.")
    return ins


def puede_formarse(bd: Session, usuario: Usuario, tarea: Tarea) -> bool:
    """¿Puede la persona formarse y evaluarse en la tarea? (su departamento o una formación activa)."""
    if usuario.rol == "admin":
        return True
    dep = iluo.departamento_de_tarea(tarea)
    if dep is None:
        return False
    return usuario.departamento_id == dep or iluo.en_formacion(bd, usuario.id, dep)


def _paso_dict(p: Paso | None) -> dict[str, Any] | None:
    if p is None:
        return None
    return {"id": p.id, "orden": p.orden, "titulo": p.titulo, "es_critico": p.es_critico}


def pregunta_dict(p: PreguntaEval, pasos: dict[int, Paso] | None = None) -> dict[str, Any]:
    """Pregunta completa (para expertos: incluye la respuesta correcta)."""
    paso = (pasos or {}).get(p.paso_id) if p.paso_id else None
    return {
        "id": p.id,
        "instruccion_id": p.instruccion_id,
        "paso_id": p.paso_id,
        "paso": _paso_dict(paso),
        "enunciado": p.enunciado,
        "opciones": list(p.opciones or []),
        "correcta": p.correcta,
        "explicacion": p.explicacion,
        "estado": p.estado,
        "aprobada_por_id": p.aprobada_por_id,
        "creada": iluo.iso(p.creada),
    }


def pregunta_a_dict(bd: Session, p: PreguntaEval) -> dict[str, Any]:
    ins = bd.get(Instruccion, p.instruccion_id)
    return pregunta_dict(p, {x.id: x for x in ins.pasos} if ins else None)


def instruccion_dict(ins: Instruccion, con_pasos: bool = False) -> dict[str, Any]:
    datos: dict[str, Any] = {
        "id": ins.id,
        "codigo": ins.codigo,
        "titulo": ins.titulo,
        "version": ins.version,
        "estado": ins.estado,
        "tarea_id": ins.tarea_id,
        "tarea": ins.tarea.nombre if ins.tarea else None,
    }
    if con_pasos:
        datos["pasos"] = [{"id": p.id, "orden": p.orden, "titulo": p.titulo, "es_critico": p.es_critico,
                           "es_seguridad": p.es_seguridad} for p in ins.pasos]
    return datos


def _validar_opciones(enunciado: str, opciones: list[Any], correcta: int) -> tuple[str, list[str], int]:
    enunciado = (enunciado or "").strip()
    if len(enunciado) < 5:
        raise HTTPException(400, "Escribe el enunciado de la pregunta.")
    limpias = [str(o).strip() for o in (opciones or [])]
    if any(not o for o in limpias):
        raise HTTPException(400, "Ninguna opción puede quedar vacía.")
    if not 2 <= len(limpias) <= 6:
        raise HTTPException(400, "Cada pregunta necesita entre 2 y 6 opciones.")
    if len({_normalizar(o) for o in limpias}) != len(limpias):
        raise HTTPException(400, "Hay opciones repetidas.")
    if not isinstance(correcta, int) or not 0 <= correcta < len(limpias):
        raise HTTPException(400, "Marca cuál es la opción correcta.")
    return enunciado[:2000], [o[:500] for o in limpias], correcta


# --------------------------------------------------------------------------- generación de preguntas


def _barajar(opciones: list[str], correcta: int, rng: random.Random) -> tuple[list[str], int]:
    """Desordena las opciones manteniendo cuál es la correcta (los modelos suelen ponerla la primera)."""
    orden = list(range(len(opciones)))
    rng.shuffle(orden)
    return [opciones[i] for i in orden], orden.index(correcta)


PREFIJO_OPCION = re.compile(r"^\s*[A-Fa-f1-6][\).:-]\s+")  # «A) », «1. », «b: »


def _indice_correcta(valor: Any, opciones: list[str]) -> int | None:
    """Interpreta «correcta» del modelo: posición desde 0 (o desde 1), letra («B», «B)»,
    «B) texto») o texto de la opción."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, list) and len(valor) == 1:  # algunos modelos devuelven [1]
        valor = valor[0]
    if isinstance(valor, str):
        v = valor.strip()
        if re.fullmatch(r"\d+", v):
            valor = int(v)
        else:
            # Primero el texto (sin «B) » delante); si no coincide, la letra.
            norm = _normalizar(PREFIJO_OPCION.sub("", v))
            for i, o in enumerate(opciones):
                if norm and _normalizar(o) == norm:
                    return i
            # «B», «B)», «Opción B», «B) texto que no coincide»
            letra = (re.fullmatch(r"(?:opci[oó]n|respuesta|letra)?\s*([A-Fa-f])\s*[\).:-]?", v, re.I)
                     or re.match(r"([A-Fa-f])[\).:-]\s", v))
            if letra:
                i = ord(letra.group(1).upper()) - ord("A")
                return i if i < len(opciones) else None
            return None
    if isinstance(valor, (int, float)):
        i = int(valor)
        if 0 <= i < len(opciones):
            return i
        if i == len(opciones):  # numerada desde 1
            return i - 1
    return None


def _campo(d: dict[str, Any], *claves: str) -> Any:
    """Primer campo presente (los modelos pequeños a veces cambian el nombre o lo ponen en inglés)."""
    for c in claves:
        if d.get(c) not in (None, "", [], {}):
            return d[c]
    return None


def _texto_opcion(o: Any) -> str:
    texto = str(_campo(o, "texto", "opcion", "text", "option") or "") if isinstance(o, dict) else str(o)
    return PREFIJO_OPCION.sub("", texto).strip()[:500]


def _parece_pregunta(enunciado: str, pasos: list[Paso]) -> bool:
    """Descarta lo que no es una pregunta: los modelos pequeños a veces devuelven como enunciado
    el propio paso copiado («1. Preparar el cambio: comprueba en el panel…»), sin interrogación."""
    e = enunciado.strip()
    if len(e) > 320 or ("?" not in e and len(e) > 160):
        return False
    if "?" not in e and re.match(r"^\d+\s*[.)-]\s*\S", e):
        return False
    normal = _normalizar(e)
    for p in pasos:
        texto = _normalizar(p.texto or "")
        if len(texto) >= 60 and texto[:60] in normal:
            return False
    return True


def _candidatas_llm(datos: Any, pasos: list[Paso], rng: random.Random) -> list[dict[str, Any]]:
    """Convierte la respuesta del modelo en preguntas válidas (descarta las mal formadas).

    Admite opciones como lista de textos, lista de objetos o diccionario {"A": ..., "B": ...};
    la correcta se identifica ANTES de quitar opciones repetidas o vacías, para que su posición
    no se desplace.
    """
    if isinstance(datos, dict):
        datos = _campo(datos, "preguntas", "questions", "items") or []
    if not isinstance(datos, list):
        return []
    por_orden = {p.orden: p for p in pasos}
    salida: list[dict[str, Any]] = []
    for d in datos:
        if not isinstance(d, dict):
            continue
        enunciado = str(_campo(d, "enunciado", "pregunta", "question") or "").strip()
        bruto = _campo(d, "opciones", "options", "alternativas")
        claves: list[str] | None = None
        if isinstance(bruto, dict):
            claves = [str(k).strip() for k in bruto]
            bruto = list(bruto.values())
        if not isinstance(bruto, list):
            continue
        textos = [_texto_opcion(o) for o in bruto]
        valor = _campo(d, "correcta", "respuesta_correcta", "respuesta", "answer", "correct")
        if claves and isinstance(valor, str) and valor.strip() in claves:
            i_correcta: int | None = claves.index(valor.strip())
        else:
            i_correcta = _indice_correcta(valor, textos)
        if i_correcta is None:  # opciones como objetos con «correcta: true»
            marcadas = [k for k, o in enumerate(bruto) if isinstance(o, dict) and o.get("correcta") is True]
            i_correcta = marcadas[0] if len(marcadas) == 1 else None
        if i_correcta is None or not textos[i_correcta]:
            continue
        clave_correcta = _normalizar(textos[i_correcta])
        opciones: list[str] = []
        for texto in textos:
            if texto and _normalizar(texto) not in {_normalizar(x) for x in opciones}:
                opciones.append(texto)
        correcta = next(i for i, o in enumerate(opciones) if _normalizar(o) == clave_correcta)
        if len(enunciado) < 8 or len(opciones) < 3 or not _parece_pregunta(enunciado, pasos):
            continue
        if _normalizar(enunciado) in {_normalizar(o) for o in opciones}:
            continue  # los modelos pequeños a veces repiten el enunciado como opción
        if len(opciones) > 4:  # como mucho 4, conservando la correcta
            resto = [i for i in range(len(opciones)) if i != correcta][:3]
            elegidas = sorted([correcta, *resto])
            correcta = elegidas.index(correcta)
            opciones = [opciones[i] for i in elegidas]
        opciones, correcta = _barajar(opciones, correcta, rng)
        numero = re.search(r"\d+", str(_campo(d, "paso", "step", "paso_numero") or ""))  # 2, "2", "Paso 2"
        paso = por_orden.get(int(numero.group())) if numero else None
        explicacion = str(_campo(d, "explicacion", "explicación", "explanation") or "").strip() or None
        salida.append({"enunciado": enunciado[:2000], "opciones": opciones, "correcta": correcta,
                       "explicacion": explicacion[:2000] if explicacion else None,
                       "paso_id": paso.id if paso else None})
    # Primero las de pasos críticos.
    criticos = {p.id for p in pasos if p.es_critico or p.es_seguridad}
    salida.sort(key=lambda c: 0 if c["paso_id"] in criticos else 1)
    return salida


def preguntas_sencillas(ins: Instruccion, rng: random.Random) -> list[dict[str, Any]]:
    """Preguntas de respaldo construidas desde los pasos (sin modelo).

    «¿Qué hay que hacer en el paso X?» con distractores de otros pasos (críticos primero),
    «¿Cuál de estos pasos es crítico?» y, si hay criterios de aceptación, una sobre el criterio.
    """
    pasos = list(ins.pasos)
    if len(pasos) < 2:
        return []
    salida: list[dict[str, Any]] = []
    orden = sorted(pasos, key=lambda p: (not (p.es_critico or p.es_seguridad), p.orden))
    for p in orden:
        otros = [o.titulo for o in pasos if o.id != p.id and _normalizar(o.titulo) != _normalizar(p.titulo)]
        otros = list(dict.fromkeys(otros))
        if not otros:
            continue
        distractores = rng.sample(otros, min(3, len(otros)))
        opciones, correcta = _barajar([p.titulo, *distractores], 0, rng)
        explicacion = f"En el paso {p.orden} hay que: {p.titulo}."
        if p.texto:
            explicacion += f" {_recortar(p.texto, 240)}"
        if p.es_critico:
            explicacion += " Es un paso crítico: hay que confirmarlo siempre."
        salida.append({"enunciado": f"¿Qué hay que hacer en el paso {p.orden}?", "opciones": opciones,
                       "correcta": correcta, "explicacion": explicacion, "paso_id": p.id})
        # Criterio de aceptación de los pasos críticos, si hay otros criterios para despistar.
        if p.es_critico and p.criterio_aceptacion:
            otros_c = list(dict.fromkeys(o.criterio_aceptacion.strip() for o in pasos
                                         if o.id != p.id and o.criterio_aceptacion
                                         and _normalizar(o.criterio_aceptacion) != _normalizar(p.criterio_aceptacion)))
            if len(otros_c) >= 2:
                distractores = rng.sample(otros_c, min(3, len(otros_c)))
                opciones, correcta = _barajar([p.criterio_aceptacion.strip(), *distractores], 0, rng)
                salida.append({
                    "enunciado": f"¿Cómo se comprueba que el paso {p.orden} («{_recortar(p.titulo, 80)}») está bien hecho?",
                    "opciones": [_recortar(o, 500) for o in opciones], "correcta": correcta,
                    "explicacion": f"El criterio de aceptación del paso {p.orden} es: {p.criterio_aceptacion.strip()}",
                    "paso_id": p.id,
                })
    criticos = [p for p in pasos if p.es_critico]
    normales = [p for p in pasos if not p.es_critico]
    if criticos and len(normales) >= 2:
        p = rng.choice(criticos)
        distractores = rng.sample(normales, min(3, len(normales)))
        opciones, correcta = _barajar([p.titulo, *[d.titulo for d in distractores]], 0, rng)
        if len({_normalizar(o) for o in opciones}) == len(opciones):
            salida.append({"enunciado": "¿Cuál de estos pasos es crítico y hay que confirmar siempre?",
                           "opciones": opciones, "correcta": correcta,
                           "explicacion": f"El paso {p.orden} («{p.titulo}») está marcado como crítico.",
                           "paso_id": p.id})
    return salida


def _mensajes(ins: Instruccion, n: int) -> list[dict[str, Any]]:
    lineas = [f"Instrucción: {ins.titulo}" + (f" ({ins.codigo})" if ins.codigo else "")]
    if ins.riesgos:
        lineas.append(f"Riesgos: {_recortar(ins.riesgos, 300)}")
    if ins.epis:
        lineas.append(f"EPI: {_recortar(ins.epis, 200)}")
    lineas.append("Pasos:")
    for p in ins.pasos:
        marca = " [CRÍTICO]" if p.es_critico else ""
        marca += " [SEGURIDAD]" if p.es_seguridad else ""
        linea = f"{p.orden}.{marca} {p.titulo}"
        if p.texto:
            linea += f": {_recortar(p.texto, 400)}"
        if p.criterio_aceptacion:
            linea += f" (Criterio de aceptación: {_recortar(p.criterio_aceptacion, 200)})"
        lineas.append(linea)
    lineas.append(f"\nEscribe {n} preguntas, la mayoría sobre los pasos críticos.")
    return [{"role": "system", "content": SISTEMA_PREGUNTAS}, {"role": "user", "content": "\n".join(lineas)}]


def generar_preguntas(bd: Session, instruccion_id: int, n: int = 6) -> int:
    """Genera hasta `n` preguntas «propuestas» para la instrucción. Devuelve cuántas ha creado.

    No repite enunciados que ya existan. No hace commit.
    """
    ins = bd.get(Instruccion, instruccion_id)
    if ins is None or not ins.pasos:
        return 0
    n = max(1, min(20, int(n)))
    rng = random.Random(f"{ins.id}-{ins.version}-{n}")
    existentes = {_normalizar(e) for e in bd.scalars(
        select(PreguntaEval.enunciado).where(PreguntaEval.instruccion_id == ins.id))}
    candidatas: list[dict[str, Any]] = []
    try:
        datos = llm.chat_json(_mensajes(ins, n), bd=bd, temperatura=0.3)
        candidatas = _candidatas_llm(datos, list(ins.pasos), rng)
    except Exception as e:  # noqa: BLE001  (el modelo puede fallar de muchas formas)
        log.warning("No se pudieron generar preguntas con el modelo para la instrucción %s: %s", ins.id, e)
    nuevas: list[dict[str, Any]] = []

    def anadir(lista: list[dict[str, Any]]) -> None:
        for c in lista:
            clave = _normalizar(c["enunciado"])
            if len(nuevas) < n and clave not in existentes:
                existentes.add(clave)
                nuevas.append(c)

    anadir(candidatas)
    if len(nuevas) < n:  # el modelo falló o repitió: se completa con preguntas sencillas
        anadir(preguntas_sencillas(ins, rng))
    for c in nuevas:
        bd.add(PreguntaEval(instruccion_id=ins.id, paso_id=c["paso_id"], enunciado=c["enunciado"],
                            opciones=c["opciones"], correcta=c["correcta"], explicacion=c["explicacion"],
                            estado="propuesta"))
    bd.flush()
    return len(nuevas)


def _trabajo_generar(bd: Session, progreso: Any, instruccion_id: int, n: int) -> dict[str, Any]:
    progreso(10, "Generando preguntas")
    return {"creadas": generar_preguntas(bd, instruccion_id, n)}


def encolar_generacion(instruccion_id: int, n: int = 6, usuario_id: int | None = None) -> int:
    """Genera las preguntas en segundo plano. Devuelve el id del trabajo."""
    return trabajos.encolar(TIPO_TRABAJO, _trabajo_generar, instruccion_id, n,
                            entidad="instruccion", entidad_id=instruccion_id, usuario_id=usuario_id)


def generando(bd: Session, instruccion_id: int) -> bool:
    n = bd.scalar(select(func.count(Trabajo.id)).where(
        Trabajo.tipo == TIPO_TRABAJO, Trabajo.entidad == "instruccion", Trabajo.entidad_id == instruccion_id,
        Trabajo.estado.in_(["pendiente", "en_curso"])))
    return bool(n)


# --------------------------------------------------------------------------- revisión del experto


def listar_preguntas(bd: Session, actor: Actor, instruccion_id: int) -> dict[str, Any]:
    ins = instruccion_para_revisar(bd, actor, instruccion_id)
    pasos = {p.id: p for p in ins.pasos}
    preguntas = bd.scalars(select(PreguntaEval).where(PreguntaEval.instruccion_id == ins.id)
                           .order_by(PreguntaEval.id)).all()
    return {
        "instruccion": instruccion_dict(ins, con_pasos=True),
        "preguntas": [pregunta_dict(p, pasos) for p in preguntas],
        "generando": generando(bd, ins.id),
    }


def _paso_valido(ins: Instruccion, paso_id: int | None) -> int | None:
    if paso_id is None:
        return None
    if paso_id not in {p.id for p in ins.pasos}:
        raise HTTPException(400, "Ese paso no pertenece a la instrucción.")
    return paso_id


def crear_pregunta(bd: Session, actor: Actor, instruccion_id: int, enunciado: str, opciones: list[str],
                   correcta: int, explicacion: str | None, paso_id: int | None) -> PreguntaEval:
    """Pregunta escrita a mano por el experto: nace aprobada."""
    ins = instruccion_para_revisar(bd, actor, instruccion_id)
    enunciado, opciones, correcta = _validar_opciones(enunciado, opciones, correcta)
    p = PreguntaEval(instruccion_id=ins.id, paso_id=_paso_valido(ins, paso_id), enunciado=enunciado,
                     opciones=opciones, correcta=correcta, explicacion=(explicacion or "").strip() or None,
                     estado="aprobada", aprobada_por_id=actor.id)
    bd.add(p)
    bd.flush()
    registrar(bd, actor, "aporto", "pregunta", p.id, _recortar(enunciado, 120),
              contexto={"instruccion_id": ins.id, "manual": True})
    return p


def cambiar_pregunta(bd: Session, actor: Actor, pregunta_id: int, cambios: dict[str, Any]) -> PreguntaEval:
    """Edita, aprueba o descarta una pregunta. `cambios` solo trae los campos enviados."""
    p = bd.get(PreguntaEval, pregunta_id)
    if p is None:
        raise HTTPException(404, "No existe esa pregunta.")
    ins = instruccion_para_revisar(bd, actor, p.instruccion_id)
    if {"enunciado", "opciones", "correcta"} & cambios.keys():
        p.enunciado, p.opciones, p.correcta = _validar_opciones(
            cambios.get("enunciado", p.enunciado), cambios.get("opciones", p.opciones),
            cambios.get("correcta", p.correcta))
    if "explicacion" in cambios:
        p.explicacion = (cambios["explicacion"] or "").strip() or None
    if "paso_id" in cambios:
        p.paso_id = _paso_valido(ins, cambios["paso_id"])
    if cambios.get("estado") is not None:
        estado = cambios["estado"]
        if estado not in ESTADOS_PREGUNTA:
            raise HTTPException(400, "Estado no válido: usa propuesta, aprobada o descartada.")
        if estado != p.estado:
            p.estado = estado
            p.aprobada_por_id = actor.id if estado == "aprobada" else None
            verbo = {"aprobada": "valido", "descartada": "rechazo"}.get(estado)
            if verbo:
                registrar(bd, actor, verbo, "pregunta", p.id, _recortar(p.enunciado, 120),
                          contexto={"instruccion_id": ins.id})
    bd.flush()
    return p


def borrar_pregunta(bd: Session, actor: Actor, pregunta_id: int) -> None:
    p = bd.get(PreguntaEval, pregunta_id)
    if p is None:
        raise HTTPException(404, "No existe esa pregunta.")
    ins = instruccion_para_revisar(bd, actor, p.instruccion_id)
    registrar(bd, actor, "rechazo", "pregunta", p.id, _recortar(p.enunciado, 120),
              resultado={"borrada": True}, contexto={"instruccion_id": ins.id, "estado": p.estado})
    bd.delete(p)
    bd.flush()


# --------------------------------------------------------------------------- cuestionario


def _tarea_para(bd: Session, actor: Actor, tarea_id: int) -> Tarea:
    tarea = bd.get(Tarea, tarea_id)
    if tarea is None:
        raise HTTPException(404, "No existe esa tarea.")
    assert actor.usuario is not None
    if not puede_formarse(bd, actor.usuario, tarea):
        raise HTTPException(403, "Esta tarea no está en tu itinerario.")
    return tarea


def _preguntas_aprobadas(bd: Session, ins: Instruccion) -> list[PreguntaEval]:
    return list(bd.scalars(select(PreguntaEval).where(PreguntaEval.instruccion_id == ins.id,
                                                      PreguntaEval.estado == "aprobada")
                           .order_by(PreguntaEval.id)).all())


def _vigente_con_preguntas(bd: Session, tarea: Tarea) -> tuple[Instruccion, list[PreguntaEval]]:
    ins = iluo.instruccion_vigente(bd, tarea.id)
    if ins is None:
        raise HTTPException(404, "Esta tarea aún no tiene una instrucción publicada.")
    preguntas = _preguntas_aprobadas(bd, ins)
    if not preguntas:
        raise HTTPException(404, "El cuestionario de esta tarea todavía no está preparado: "
                                 "faltan preguntas aprobadas por un experto.")
    return ins, preguntas


def clave_opcion(pregunta_id: int, i: int) -> str:
    """Identificador opaco de una opción del cuestionario.

    No revela la posición original de la opción: en las preguntas escritas a mano la correcta
    suele ser la primera, así que enviar el índice daría una pista de la respuesta.
    """
    firma = hmac.new(ajustes().secreto_jwt.encode(), f"opcion:{pregunta_id}:{i}".encode(), hashlib.sha256)
    return firma.hexdigest()[:12]


def _indice_elegido(p: PreguntaEval, valor: Any) -> int | None:
    """Opción elegida: la clave opaca del cuestionario (o, por compatibilidad, el índice original)."""
    n = len(p.opciones or [])
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, int):
        return valor if 0 <= valor < n else None
    if isinstance(valor, str):
        for i in range(n):
            if hmac.compare_digest(clave_opcion(p.id, i), valor):
                return i
    return None


def cuestionario(bd: Session, actor: Actor, tarea_id: int) -> dict[str, Any]:
    """Preguntas aprobadas de la instrucción vigente en orden aleatorio, SIN la respuesta correcta.

    Cada opción lleva una `clave` opaca, que es lo que se envía al responder.
    """
    tarea = _tarea_para(bd, actor, tarea_id)
    ins, preguntas = _vigente_con_preguntas(bd, tarea)
    pasos = {p.id: p for p in ins.pasos}
    rng = random.SystemRandom()
    rng.shuffle(preguntas)
    salida = []
    for p in preguntas:
        opciones = [{"clave": clave_opcion(p.id, i), "texto": t} for i, t in enumerate(p.opciones or [])]
        rng.shuffle(opciones)
        paso = pasos.get(p.paso_id) if p.paso_id else None
        salida.append({"id": p.id, "enunciado": p.enunciado, "opciones": opciones,
                       "paso": {"orden": paso.orden, "titulo": paso.titulo, "es_critico": paso.es_critico}
                       if paso else None})
    cfg = iluo.configuracion(bd)
    intentos = bd.scalar(select(func.count(IntentoEval.id)).where(
        IntentoEval.usuario_id == actor.id, IntentoEval.instruccion_id == ins.id)) or 0
    return {
        "tarea": {"id": tarea.id, "codigo": tarea.codigo, "nombre": tarea.nombre},
        "instruccion": {"id": ins.id, "codigo": ins.codigo, "titulo": ins.titulo, "version": ins.version},
        "umbral": cfg["umbral_cuestionario"],
        "intentos_previos": intentos,
        "preguntas": salida,
    }


def siguiente_paso(fila: NivelIluo, ev: iluo.Evidencias) -> str | None:
    """Lo siguiente que le falta a la persona para subir de nivel, en lenguaje claro."""
    if fila.nivel >= 4:
        return None
    for r in ev.requisitos():
        if r["nivel"] <= max(fila.nivel + 1, 1) and not r["cumplido"]:
            if r["nivel"] <= fila.nivel and ev.nivel < fila.nivel and not fila.requiere_reevaluacion:
                # Nivel puesto a mano (ajuste o matriz en papel): para subir cuentan también las
                # evidencias de los niveles que ya tiene, y sin esta aclaración el texto confunde.
                return f"{r['falta']} El nivel actual se asignó a mano y aún no tiene evidencias en CidIA."
            return r["falta"]
    for r in ev.requisitos():
        if not r["cumplido"]:
            return r["falta"]
    return None


def responder(bd: Session, actor: Actor, tarea_id: int, respuestas: dict[int, Any],
              instruccion_id: int | None = None) -> dict[str, Any]:
    """Corrige en el servidor, guarda el intento, registra xAPI y recalcula el nivel ILUO.

    `respuestas` = {pregunta_id: clave de la opción elegida} (o su índice original).
    """
    tarea = _tarea_para(bd, actor, tarea_id)
    ins, preguntas = _vigente_con_preguntas(bd, tarea)
    if instruccion_id is not None and instruccion_id != ins.id:
        raise HTTPException(409, "Se ha publicado una versión nueva de la instrucción mientras respondías. "
                                 "Vuelve a empezar el cuestionario.")
    validas = {p.id for p in preguntas}
    if not respuestas or not set(respuestas) & validas:
        raise HTTPException(400, "No has respondido ninguna pregunta.")
    pasos = {p.id: p for p in ins.pasos}
    cfg = iluo.configuracion(bd)
    aciertos = 0
    correccion = []
    elegidas: dict[str, int | None] = {}
    for p in preguntas:  # las no respondidas cuentan como fallo
        elegida = _indice_elegido(p, respuestas.get(p.id))
        if p.id in respuestas:
            elegidas[str(p.id)] = elegida
        acierto = elegida is not None and elegida == p.correcta
        aciertos += acierto
        datos = pregunta_dict(p, pasos)
        datos.pop("aprobada_por_id", None)
        correccion.append({**datos, "elegida": elegida, "acierto": acierto})
    total = len(preguntas)
    puntuacion = aciertos / total
    aprobado = puntuacion + 1e-9 >= cfg["umbral_cuestionario"]
    intento = IntentoEval(usuario_id=actor.id, instruccion_id=ins.id, respuestas=elegidas,
                          aciertos=aciertos, total=total, puntuacion=puntuacion, aprobado=aprobado)
    bd.add(intento)
    bd.flush()
    registrar(bd, actor, "aprobo" if aprobado else "suspendio", "cuestionario", ins.id,
              f"Cuestionario · {tarea.nombre} (v{ins.version})",
              resultado={"score": round(puntuacion, 4), "success": aprobado, "aciertos": aciertos, "total": total},
              contexto={"tarea_id": tarea.id, "instruccion_id": ins.id, "intento_id": intento.id})
    antes = iluo.fila_de(bd, actor.id, tarea.id)
    nivel_antes = antes.nivel if antes else 0
    fila, ev = iluo.recalcular_con_evidencias(bd, actor.id, tarea.id)
    return {
        "intento_id": intento.id,
        "aprobado": aprobado,
        "aciertos": aciertos,
        "total": total,
        "puntuacion": round(puntuacion, 4),
        "umbral": cfg["umbral_cuestionario"],
        "correccion": correccion,
        "nivel": {"nivel": fila.nivel, "letra": iluo.nivel_letra(fila.nivel), "nombre": iluo.nivel_nombre(fila.nivel),
                  "subio": fila.nivel > nivel_antes},
        "siguiente": siguiente_paso(fila, ev),
    }


# --------------------------------------------------------------------------- observación en el puesto


def _para_observar(bd: Session, actor: Actor, usuario_id: int, tarea_id: int) -> tuple[Usuario, Tarea, Instruccion]:
    usuario = bd.get(Usuario, usuario_id)
    tarea = bd.get(Tarea, tarea_id)
    if usuario is None or tarea is None:
        raise HTTPException(404, "No existe esa persona o esa tarea.")
    if not (actor.es_admin or actor.rol == "jefe") or not iluo.puede_evaluar(bd, actor, usuario, tarea):
        raise HTTPException(403, "Solo el jefe del departamento de la tarea puede observar a esta persona.")
    ins = iluo.instruccion_vigente(bd, tarea.id)
    if ins is None or not ins.pasos:
        raise HTTPException(404, "Esta tarea aún no tiene una instrucción publicada con pasos.")
    return usuario, tarea, ins


def observacion_dict(bd: Session, o: Observacion) -> dict[str, Any]:
    evaluador = bd.get(Usuario, o.evaluador_id) if o.evaluador_id else None
    lista = list(o.lista or [])
    return {
        "id": o.id,
        "usuario_id": o.usuario_id,
        "tarea_id": o.tarea_id,
        "instruccion_id": o.instruccion_id,
        "evaluador": evaluador.nombre if evaluador else None,
        "aprobada": o.aprobada,
        "comentario": o.comentario,
        "fecha": iluo.iso(o.creada),
        "pasos": len(lista),
        "pasos_ok": sum(1 for x in lista if x.get("ok")),
        "criticos_fallidos": sum(1 for x in lista if x.get("critico") and x.get("ok") is False),
        "lista": lista,
    }


def plantilla_observacion(bd: Session, actor: Actor, usuario_id: int, tarea_id: int) -> dict[str, Any]:
    """Lista de comprobación: todos los pasos de la instrucción vigente, con los críticos destacados."""
    usuario, tarea, ins = _para_observar(bd, actor, usuario_id, tarea_id)
    fila = iluo.fila_de(bd, usuario.id, tarea.id)
    previas = bd.scalars(select(Observacion).where(Observacion.usuario_id == usuario.id,
                                                   Observacion.tarea_id == tarea.id)
                         .order_by(Observacion.creada.desc()).limit(5)).all()
    return {
        "persona": {"id": usuario.id, "nombre": usuario.nombre, "puesto": usuario.puesto.nombre if usuario.puesto else None},
        "tarea": {"id": tarea.id, "codigo": tarea.codigo, "nombre": tarea.nombre, "riesgos_prl": tarea.riesgos_prl},
        "instruccion": instruccion_dict(ins),
        "nivel": {"nivel": fila.nivel if fila else 0, "letra": iluo.nivel_letra(fila.nivel if fila else 0),
                  "caducado": iluo.caducado(fila)},
        "lista": [{"paso_id": p.id, "orden": p.orden, "titulo": p.titulo, "texto": p.texto,
                   "critico": p.es_critico, "seguridad": p.es_seguridad, "criterio": p.criterio_aceptacion}
                  for p in ins.pasos],
        "previas": [{k: v for k, v in observacion_dict(bd, o).items() if k != "lista"} for o in previas],
    }


def registrar_observacion(bd: Session, actor: Actor, usuario_id: int, tarea_id: int, marcas: list[dict[str, Any]],
                          aprobada: bool, comentario: str | None, instruccion_id: int | None = None) -> dict[str, Any]:
    """Guarda la observación (textos de los pasos tomados del servidor), registra xAPI y recalcula ILUO."""
    usuario, tarea, ins = _para_observar(bd, actor, usuario_id, tarea_id)
    if instruccion_id is not None and instruccion_id != ins.id:
        raise HTTPException(409, "Se ha publicado una versión nueva de la instrucción. Vuelve a abrir la lista.")
    por_paso = {int(m["paso_id"]): m for m in marcas if m.get("paso_id") is not None}
    ajenos = set(por_paso) - {p.id for p in ins.pasos}
    if ajenos:
        raise HTTPException(400, "La lista incluye pasos que no son de la instrucción vigente.")
    lista = []
    for p in ins.pasos:
        m = por_paso.get(p.id)
        if m is None or m.get("ok") is None:
            raise HTTPException(400, f"Marca el paso {p.orden} («{_recortar(p.titulo, 60)}») como correcto o no.")
        lista.append({"paso_id": p.id, "orden": p.orden, "texto": p.titulo, "critico": p.es_critico,
                      "ok": bool(m["ok"]), "nota": (str(m.get("nota") or "").strip()[:1000] or None)})
    if aprobada and any(x["critico"] and not x["ok"] for x in lista):
        raise HTTPException(400, "No se puede aprobar con un paso crítico mal hecho. Marca la observación como no superada.")
    obs = Observacion(evaluador_id=actor.id, usuario_id=usuario.id, tarea_id=tarea.id, instruccion_id=ins.id,
                      lista=lista, aprobada=bool(aprobada), comentario=(comentario or "").strip()[:2000] or None)
    bd.add(obs)
    bd.flush()
    ok = sum(1 for x in lista if x["ok"])
    registrar(bd, actor, "observo", "observacion", obs.id, f"{usuario.nombre} · {tarea.nombre}",
              resultado={"success": obs.aprobada, "pasos": len(lista), "pasos_ok": ok,
                         "score": round(ok / len(lista), 4)},
              contexto={"usuario_id": usuario.id, "tarea_id": tarea.id, "instruccion_id": ins.id})
    antes = iluo.fila_de(bd, usuario.id, tarea.id)
    nivel_antes = antes.nivel if antes else 0
    fila, ev = iluo.recalcular_con_evidencias(bd, usuario.id, tarea.id)
    return {
        "observacion": observacion_dict(bd, obs),
        "nivel": {"nivel": fila.nivel, "letra": iluo.nivel_letra(fila.nivel), "nombre": iluo.nivel_nombre(fila.nivel),
                  "subio": fila.nivel > nivel_antes},
        "siguiente": siguiente_paso(fila, ev),
    }


# --------------------------------------------------------------------------- pendientes


def _cuestionarios_de(bd: Session, actor: Actor) -> list[dict[str, Any]]:
    from cidia.servicios import progreso  # import tardío: progreso usa este módulo

    assert actor.usuario is not None
    cfg = iluo.configuracion(bd)
    tareas = progreso.tareas_de(bd, actor.usuario)
    # Una consulta por tipo de dato para todas las tareas (esto se calcula también para el
    # contador del menú en cada cambio de pantalla).
    vigentes = iluo.instrucciones_vigentes(bd, [t.id for t in tareas])
    ins_ids = [i.id for i in vigentes.values()]
    aprobadas: dict[int, int] = {}
    por_instruccion: defaultdict[int, list[IntentoEval]] = defaultdict(list)
    filas: dict[int, NivelIluo] = {}
    if ins_ids:
        aprobadas = {i: n for i, n in bd.execute(
            select(PreguntaEval.instruccion_id, func.count(PreguntaEval.id))
            .where(PreguntaEval.instruccion_id.in_(ins_ids), PreguntaEval.estado == "aprobada")
            .group_by(PreguntaEval.instruccion_id))}
        for it in bd.scalars(select(IntentoEval).where(IntentoEval.usuario_id == actor.id,
                                                       IntentoEval.instruccion_id.in_(ins_ids))
                             .order_by(IntentoEval.creado.desc())):
            por_instruccion[it.instruccion_id].append(it)
        filas = {f.tarea_id: f for f in bd.scalars(select(NivelIluo).where(
            NivelIluo.usuario_id == actor.id, NivelIluo.tarea_id.in_(list(vigentes))))}
    salida = []
    for tarea in tareas:
        ins = vigentes.get(tarea.id)
        if ins is None:
            continue
        n = aprobadas.get(ins.id, 0)
        if not n:
            continue
        intentos = por_instruccion.get(ins.id, [])
        fila = filas.get(tarea.id)
        # Solo cuenta un aprobado dentro de la ventana de validez (el mismo criterio que el nivel ILUO).
        desde = iluo.inicio_ventana(fila, cfg)
        aprobado = any(i.aprobado and i.creado >= desde for i in intentos)
        reeval = bool(fila and fila.requiere_reevaluacion)
        ultimo = intentos[0] if intentos else None
        salida.append({
            "tarea_id": tarea.id, "codigo": tarea.codigo, "tarea": tarea.nombre,
            "puesto": tarea.puesto.nombre if tarea.puesto else None,
            "instruccion_id": ins.id, "titulo": ins.titulo, "version": ins.version, "preguntas": n,
            "aprobado": aprobado, "intentos": len(intentos), "requiere_reevaluacion": reeval,
            "aprobado_caducado": not aprobado and any(i.aprobado for i in intentos),
            "pendiente": not aprobado or reeval,
            "nivel": fila.nivel if fila else 0, "letra": iluo.nivel_letra(fila.nivel if fila else 0),
            "ultimo": {"fecha": iluo.iso(ultimo.creado), "puntuacion": round(ultimo.puntuacion, 4),
                       "aprobado": ultimo.aprobado} if ultimo else None,
        })
    salida.sort(key=lambda c: (not c["pendiente"], c["tarea"]))
    return salida


def _preguntas_por_revisar(bd: Session, actor: Actor) -> list[dict[str, Any]]:
    q = (select(Instruccion).join(Tarea, Tarea.id == Instruccion.tarea_id).join(Puesto, Puesto.id == Tarea.puesto_id)
         .options(contains_eager(Instruccion.tarea))
         .where(Instruccion.estado != "obsoleta").order_by(Tarea.nombre, Instruccion.version.desc()))
    if not actor.es_admin:
        q = q.where(Puesto.departamento_id == actor.departamento_id)
    instrucciones = list(bd.scalars(q).unique().all())
    ids = [i.id for i in instrucciones]
    cuentas: defaultdict[int, dict[str, int]] = defaultdict(dict)
    en_curso: set[int] = set()
    if ids:
        for iid, estado, n in bd.execute(select(PreguntaEval.instruccion_id, PreguntaEval.estado, func.count())
                                         .where(PreguntaEval.instruccion_id.in_(ids))
                                         .group_by(PreguntaEval.instruccion_id, PreguntaEval.estado)):
            cuentas[iid][estado] = n
        en_curso = set(bd.scalars(select(Trabajo.entidad_id).where(
            Trabajo.tipo == TIPO_TRABAJO, Trabajo.entidad == "instruccion", Trabajo.entidad_id.in_(ids),
            Trabajo.estado.in_(["pendiente", "en_curso"]))))
    salida = []
    for ins in instrucciones:
        c = cuentas.get(ins.id, {})
        salida.append({**instruccion_dict(ins), "propuestas": c.get("propuesta", 0),
                       "aprobadas": c.get("aprobada", 0), "descartadas": c.get("descartada", 0),
                       "generando": ins.id in en_curso})
    salida.sort(key=lambda i: (-i["propuestas"], i["estado"] != "publicada", i["tarea"] or ""))
    return salida


def _observaciones_sugeridas(bd: Session, actor: Actor) -> list[dict[str, Any]]:
    """Personas con nivel L (o reevaluación superada en L) a las que les falta la observación."""
    q = (select(NivelIluo, Usuario, Tarea).join(Usuario, Usuario.id == NivelIluo.usuario_id)
         .join(Tarea, Tarea.id == NivelIluo.tarea_id).join(Puesto, Puesto.id == Tarea.puesto_id)
         .where(NivelIluo.nivel == 2, Usuario.activo.is_(True), Tarea.activa.is_(True)))
    if not actor.es_admin:
        q = q.where(Puesto.departamento_id == actor.departamento_id)
    salida = []
    for fila, usuario, tarea in bd.execute(q).all():
        if usuario.id == actor.id or not iluo.puede_evaluar(bd, actor, usuario, tarea):
            continue
        datos = fila.evidencias or {}
        if datos.get("observacion"):
            continue  # ya observada: le falta otra cosa (p. ej. una ejecución sin consultas en críticos)
        salida.append({"usuario_id": usuario.id, "nombre": usuario.nombre, "tarea_id": tarea.id,
                       "codigo": tarea.codigo, "tarea": tarea.nombre, "nivel": fila.nivel, "letra": "L",
                       "desde": iluo.iso(fila.desde),
                       "motivo": "Ya ejecuta con apoyo (L): falta la observación en el puesto para pasar a U."})
    salida.sort(key=lambda s: s["desde"] or "")
    return salida


def pendientes(bd: Session, actor: Actor) -> dict[str, Any]:
    """Lo que cada persona tiene por hacer en evaluación, según su rol."""
    datos: dict[str, Any] = {"cuestionarios": _cuestionarios_de(bd, actor)}
    if actor.es_experto:
        datos["preguntas"] = _preguntas_por_revisar(bd, actor)
    if actor.es_jefe:
        datos["observaciones"] = _observaciones_sugeridas(bd, actor)
    return datos


def contar_pendientes(bd: Session, actor: Actor) -> int:
    """Número para el contador del menú «Evaluación»."""
    if actor.es_invitado:
        return 0
    d = pendientes(bd, actor)
    n = sum(1 for c in d["cuestionarios"] if c["pendiente"])
    n += sum(i["propuestas"] for i in d.get("preguntas", []))
    n += len(d.get("observaciones", []))
    return n
