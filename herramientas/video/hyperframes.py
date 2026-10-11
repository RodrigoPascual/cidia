"""Montaje v2 de CidIA con HyperFrames: diseño, cámara, subtítulos, música y vídeo final.

    python herramientas/video/hyperframes.py todo <proyecto.json> --grabaciones <carpeta> --voces <carpeta>
           --trabajo <carpeta> --salida <video.mp4> [--bloques A,B] [--workers 4]

Pasos (cada uno se puede lanzar suelto con el mismo --trabajo):
  escenas   montaje.py --limpio: por escena, vídeo limpio con su línea de tiempo y mapa de tiempos.
  linea     línea de tiempo global (linea.json): duración y transición de cada pieza, bloques de render, cámara,
            subtítulos, voz, música, efectos y capítulos.
  componer  proyecto HyperFrames en <trabajo>/hf: una composición por bloque (bloque-<id>.html) con los datos del
            bloque, el CSS y el director (hyperframes/cidia-v2.css y cidia-v2.js), fuentes OFL, GSAP y medios.
  render    cada bloque con la CLI de HyperFrames 0.8.145 en local (--gpu: NVENC), sin telemetría ni
            actualizaciones; deja <trabajo>/bloques/<id>.mp4.
  audio     narración, micrófono, música y efectos (musica.py) en <trabajo>/mezcla.wav.
  final     une los bloques (cada uno recortado a sus fotogramas), normaliza la voz a -16 LUFS (loudnorm en dos
            pasadas) y codifica con NVENC (H.264, VBR de calidad constante 19, tope de 20 Mb/s) + AAC,
            con subtítulos (.srt y pista), capítulos (.capitulos.txt y en el MP4) e informe.

Guía de estilo: 04_VIDEO/v2/notas/guia-estilo.md. Decisión de herramientas: 04_VIDEO/v2/notas/repos.md.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import wave
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from comun import AQUI, HERR, REPO, en_entorno  # noqa: E402

en_entorno(['PIL', 'numpy'])

import numpy as np  # noqa: E402
from PIL import Image, ImageFont  # noqa: E402

import montaje  # noqa: E402
import musica  # noqa: E402
from comun import cargar_proyecto, correr, ffmpeg  # noqa: E402

FPS, W, H, TASA = 30, 1920, 1080, 48000
HF = HERR / 'hyperframes'
ACTIVOS = AQUI / 'hyperframes'
GSAP = HF / 'node_modules' / 'gsap' / 'dist' / 'gsap.min.js'
F_ARCHIVO = HERR / 'fuentes' / 'v2' / 'Archivo[wdth,wght].ttf'
F_MONO = HERR / 'fuentes' / 'v2' / 'JetBrainsMono[wght].ttf'
F_FIRA = HERR / 'fuentes'
PALETA_AVATAR = ['#1F8A70', '#2F6FBF', '#8A6D00', '#7A4FB5', '#C8442F', '#3A4048', '#0E7C86']  # la de la app (ui/index.tsx)

PERSONAS = {
    'carmen': ('Carmen Díaz', 'experta de Producción'),
    'lucia': ('Lucía Herrero', 'operaria recién llegada'),
    'marta': ('Marta Sanz', 'técnica de la línea 2'),
    'pedro': ('Pedro Ruiz', 'operario de prensas'),
    'javier': ('Javier Martín', 'jefe de Producción'),
    'ana': ('Ana López', 'responsable de Oficina técnica'),
    'luis': ('Luis García', 'recién llegado, nivel 1'),
    'nuria': ('Nuria Gil', 'experta de Mantenimiento'),
    'admin': ('Administración', 'toda la planta'),
}

# Glosario de chips de las bases (guía, apartado 9): el mismo punto se llama igual en todo el vídeo.
GLOSARIO = {
    'digitalización de procedimientos operativos': 'Procedimientos digitalizados',
    'captura del conocimiento de operarios expertos': 'Captura del saber experto',
    'generación automática de instrucciones': 'Instrucciones automáticas',
    'documentación técnica convertida en formación': 'Documentación a formación',
    'bases de conocimiento inteligentes': 'Base de conocimiento',
    'gestión centralizada del conocimiento': 'Gestión centralizada',
    'formación contextualizada en el puesto': 'Formación en el puesto',
    'itinerarios de aprendizaje personalizados': 'Itinerarios personalizados',
    'itinerarios personalizados': 'Itinerarios personalizados',
    'micro-learning industrial': 'Micro-learning',
    'tutorización inteligente': 'Tutor inteligente',
    'adaptado al perfil': 'Adaptado al perfil',
    'acceso inmediato a contenidos': 'Acceso inmediato',
    'asistencia guiada paso a paso': 'Guía paso a paso',
    'apoyo a la toma de decisiones': 'Apoyo a decisiones',
    'recomendaciones según el contexto': 'Recomendaciones en contexto',
    'validación de tareas realizadas': 'Validación de tareas',
    'seguimiento de progresos individuales': 'Progreso individual',
    'necesidades formativas': 'Necesidades formativas',
    'evaluación continua': 'Evaluación continua',
    'seguimiento de hitos de aprendizaje': 'Hitos de aprendizaje',
    'seguimiento de hitos': 'Hitos de aprendizaje',
    'registro de actividades': 'Registro de actividad',
    'trazabilidad hasta versión y autor': 'Trazabilidad versión y autor',
    'indicadores de desempeño': 'Indicadores de desempeño',
    'validación (cuestionario)': 'Cuestionario',
    'validación (observación)': 'Observación en el puesto',
    'validación (cuestionario y observación)': 'Cuestionario y observación',
    'evidencias de competencia': 'Evidencias de competencia',
    'pasaporte digital de habilidades': 'Pasaporte de habilidades',
    'certificación por puesto o tarea': 'Certificación por tarea',
    'gestión de niveles': 'Gestión de niveles',
    'renovación y actualización': 'Renovación y caducidad',
    'auditoría y trazabilidad': 'Auditoría',
    'proteger el conocimiento experto': 'Proteger el saber experto',
    'proteger el conocimiento experto (privacidad)': 'Privacidad',
    'implantación sencilla y económica': 'Implantación sencilla',
    'base tecnológica e ia relevante': 'IA relevante',
    'copiloto inteligente': 'Copiloto inteligente',
    'garantizar la correcta ejecución': 'Ejecución correcta',
    'incrementar la polivalencia': 'Polivalencia',
    'atraer a nuevas generaciones': 'Nuevas generaciones',
    'aplicable en entornos reales': 'Entorno real',
    'mejoras añadidas': 'Mejoras añadidas',
}
NOMBRES_CORTOS = {  # para las listas de las teselas del mapa (una línea)
    'App de escritorio y acceso público': 'App y acceso público',
    'Mi perfil: contraseña y memoria personal': 'Mi perfil y memoria',
    'Nota de voz convertida en ficha': 'Nota de voz a ficha',
    'Cuestionario aprobado por un experto': 'Cuestionario aprobado',
    'Organización, personas e identidad': 'Organización y personas',
    'Registro xAPI, auditoría y estado': 'Registro xAPI y auditoría',
    'Versiones nuevas y reevaluación': 'Versiones y reevaluación',
    'Copiloto con fuentes, por voz': 'Copiloto con fuentes',
    'Foto del resultado, revisada': 'Foto del resultado',
    'Aportaciones desde la planta': 'Aportaciones de planta',
    'Itinerario y micro-lecciones': 'Itinerario y lecciones',
}
# Medio círculo: los tres puntos simplificados del alcance y la integración (conectores LDAP y OIDC preparados, ◐ en
# docs/estado-mvp.md). La leyenda dice «simplificado o preparado».
SIMPLIFICADOS = {'Adaptado al perfil', 'Apoyo a decisiones', 'Recomendaciones en contexto', 'Integración'}
TAREAS_CORTAS = {
    'El servidor transcribe el vídeo, detecta los pasos y revisa cada imagen': 'Transcribe, separa pasos y revisa imágenes',
    'El copiloto busca en los documentos públicos': 'Busca en lo público',
    'El servidor transcribe la nota y la ordena en una ficha': 'Transcribe y ordena la nota',
    'El servidor transcribe la nota y la ordena': 'Transcribe y ordena la nota',
    'Transcribe la respuesta y prepara la siguiente pregunta': 'Transcribe y prepara la pregunta',
    'El copiloto prepara la respuesta en el servidor': 'Prepara la respuesta',
    'Transcribe la voz y responde con la instrucción': 'Transcribe y responde',
    'Ejecutando en un contenedor aislado del servidor': 'Ejecuta en un contenedor aislado',
    'Javier corrige el título, el problema, la causa y la solución': 'Javier corrige la aportación',
    'Javier marca los ocho pasos y escribe el comentario': 'Javier marca los ocho pasos',
    'Guardando el recuerdo en el servidor': 'Guarda el recuerdo',
    'Publicando e indexando la instrucción': 'Publica e indexa',
}


# ---------------------------------------------------------------------------------------------- utilidades
def leer(p: Path) -> dict:
    return json.loads(Path(p).read_text(encoding='utf-8'))


def escribir(p: Path, d) -> None:
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=1, default=str), encoding='utf-8')


def fot(s: float) -> float:
    """Redondea a fotogramas (hacia abajo)."""
    return math.floor(s * FPS + 1e-6) / FPS


def sin_tildes(t: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn').lower()


def color_avatar(nombre: str) -> str:
    return PALETA_AVATAR[sum(ord(c) for c in nombre) % len(PALETA_AVATAR)]


def iniciales(nombre: str) -> str:
    return ''.join(p[0] for p in nombre.split()[:2]).upper()


def persona_de(usuario: str | None, nombre: str | None = None, rol: str | None = None) -> dict:
    if not usuario and not nombre:
        return {'nombre': 'Sin iniciar sesión', 'rol': 'app de escritorio', 'icono': 'log-in', 'color': '#3A4048', 'iniciales': ''}
    if usuario in PERSONAS:
        nombre, rol0 = PERSONAS[usuario]
        rol = rol or rol0
    return {'nombre': nombre, 'rol': rol or '', 'iniciales': iniciales(nombre), 'color': color_avatar(nombre)}


def quien_es(p: dict) -> str | None:
    """Quién sale en la escena: la cuenta de la sesión o, en la app de escritorio, la que inicia sesión en la toma."""
    return p.get('usuario') or p.get('cuenta_acceso')


def chip_base(texto: str) -> dict:
    clave = texto.strip().lower()
    corto = GLOSARIO.get(clave)
    if not corto:
        base = re.sub(r'\s*\(.*?\)\s*', '', clave).strip()
        corto = GLOSARIO.get(base)
        if not corto:
            m = re.match(r'(.*?)\s*\((.*)\)', texto.strip())
            corto = (m.group(1) if m else texto.strip())
            corto = corto[0].upper() + corto[1:]
    return {'texto': html.escape(corto), 'medio': corto in SIMPLIFICADOS}


def tarea_corta(t: str) -> str:
    t = TAREAS_CORTAS.get(t, t)
    if len(t) > 40:
        palabras = t.split()
        while len(' '.join(palabras)) > 38 and len(palabras) > 3:
            palabras.pop()
        t = ' '.join(palabras)
    return t


# ---------------------------------------------------------------------------------------------- texto
_FUENTES: dict = {}


def fuente_pil(familia: str, tam: int, peso: int = 400, anchura: int = 100) -> ImageFont.FreeTypeFont:
    clave = (familia, tam, peso, anchura)
    if clave in _FUENTES:
        return _FUENTES[clave]
    if familia == 'archivo':
        f = ImageFont.truetype(str(F_ARCHIVO), tam)
        ejes = f.get_variation_axes()
        vals = []
        for e in ejes:
            nombre = e.get('name', b'')
            nombre = nombre.decode() if isinstance(nombre, bytes) else str(nombre)
            vals.append(anchura if 'idth' in nombre else peso)
        f.set_variation_by_axes(vals)
    else:
        nombres = {400: 'Regular', 500: 'Medium', 600: 'SemiBold', 700: 'Bold'}
        f = ImageFont.truetype(str(F_FIRA / f'FiraSans-{nombres.get(peso, "Regular")}.ttf'), tam)
    _FUENTES[clave] = f
    return f


def partir(texto: str, f: ImageFont.FreeTypeFont, ancho: int, maximo: int = 3) -> list[str]:
    """Líneas equilibradas que caben en `ancho`, sin dejar una palabra sola al final."""
    palabras = texto.split()
    medir = lambda s: f.getlength(s)  # noqa: E731
    if medir(texto) <= ancho:
        return [texto]
    mejor = None
    for n in range(2, maximo + 1):
        # Reparto voraz equilibrado: objetivo = longitud total / n.
        objetivo = medir(texto) / n
        lineas, actual = [], []
        for w in palabras:
            prueba = ' '.join(actual + [w])
            if actual and (medir(prueba) > ancho or (medir(' '.join(actual)) >= objetivo and len(lineas) < n - 1)):
                lineas.append(' '.join(actual))
                actual = [w]
            else:
                actual.append(w)
        lineas.append(' '.join(actual))
        if all(medir(x) <= ancho for x in lineas) and len(lineas) <= n:
            if len(lineas[-1].split()) == 1 and len(lineas) > 1:
                ant = lineas[-2].split()
                if len(ant) > 1:
                    lineas[-2], lineas[-1] = ' '.join(ant[:-1]), ant[-1] + ' ' + lineas[-1]
            mejor = lineas
            break
    return mejor or [texto]


def lineas_html(lineas: list[str]) -> list[str]:
    return [html.escape(x) for x in lineas]


RESALTE = re.compile(r'(\b\d+(?:[.,]\d+)?\s?(?:N·m|%|€|días|minutos|segundos|pasos|preguntas|temas|bar)\b|\b\d{1,3}(?:\.\d{3})+\s?€|'
                     r'\bIT-\d{3}\b|\bS4\b|\bM18\b|\bnivel [ILUO]\b|\bxAPI\b|\bILUO\b)')


def resaltar(texto: str) -> str:
    t = html.escape(texto)
    n = [0]

    def f(m):
        n[0] += 1
        return f'<em>{m.group(0)}</em>' if n[0] <= 2 else m.group(0)
    return RESALTE.sub(f, t)


# ---------------------------------------------------------------------------------------------- cámara
ADELANTO_HF = -0.067  # s: en el render, cada fotograma de un vídeo sale unos dos fotogramas más tarde que su tiempo (medido en un desplazamiento)
REPOSO = (960.0, 540.0, 1.0)
ZMAX = 1.55
ZMIN_UTIL = 1.12


def encuadre(caja: tuple[float, float, float, float], zmax: float = ZMAX) -> tuple[float, float, float]:
    x, y, w, h = caja
    w2, h2 = max(w, 120) * 1.12, max(h, 68) * 1.12
    z = min(zmax, W / w2, H / h2)
    if z < ZMIN_UTIL:
        return REPOSO
    cx = min(max(x + w / 2, W / 2 / z), W - W / 2 / z)
    cy = min(max(y + h / 2, H / 2 / z), H - H / 2 / z)
    return (round(cx, 1), round(cy, 1), round(z, 3))


def objetivo_de(a: dict) -> tuple[str, tuple | None]:
    tipo = a['tipo']
    el, cf = a.get('elemento'), a.get('cursor_fin')
    if tipo in ('resaltar', 'resaltarTexto') and el:
        return 'resaltar', encuadre((el['x'], el['y'], el['w'], el['h']))
    if tipo in ('clic', 'clicTexto', 'hover', 'hoverTexto', 'seleccionar', 'subir') and cf:
        return 'clic', encuadre((cf[0] - 450, cf[1] - 253, 900, 506), 1.4)
    if tipo == 'escribir' and el:
        cx, cy = el['x'] + el['w'] / 2, el['y'] + el['h'] / 2
        return 'escribir', encuadre((cx - 550, cy - 200, 1100, 400))
    if tipo == 'mantenerMicro' and el:
        cx, cy = el['x'] + el['w'] / 2, el['y'] + el['h'] / 2
        return 'micro', encuadre((cx - 760, cy - 430, 1520, 860), 1.28)
    if tipo in ('ir', 'scroll', 'recargar'):
        return 'reposo', REPOSO
    return 'nada', None


def en_centro(obj: tuple, actual: tuple) -> bool:
    """¿Cae el objetivo dentro del 60 % central de la vista actual (y con un zoom parecido)?"""
    cx, cy, z = actual
    vw, vh = W / z, H / z
    ox, oy, oz = obj
    return abs(ox - cx) <= 0.3 * vw and abs(oy - cy) <= 0.3 * vh and abs(oz - z) <= 0.2


def camara(mapa: dict, fin_reposo: float | None, resultado_ini: float | None) -> list[list[float]]:
    """Fotogramas clave [t0, t1, cx, cy, z] (segundos de la escena): la cámara se acerca a cada acción y vuelve a reposo
    con las reglas de la guía (apartado 8.2): arranca 150 ms antes de la acción, llega con la curva de cámara en 0,6 a
    0,9 s, se queda al menos 1,2 s, zona muerta en el 60 % central, reposo en las esperas, la navegación y el resultado."""
    dur = mapa['duracion']
    limite = (resultado_ini - 0.15) if resultado_ini is not None else dur
    if fin_reposo is not None:
        limite = min(limite, fin_reposo - 0.7)
    eventos = []
    acciones = mapa['acciones']
    for k, a in enumerate(acciones):
        if not a.get('visible') or a['ini'] >= limite - 0.4:
            continue
        clase, obj = objetivo_de(a)
        # Un clic que lleva a esperar algo nuevo (navegación, búsqueda, envío) no se encuadra: la pantalla cambia.
        sig = acciones[k + 1] if k + 1 < len(acciones) else None
        if clase == 'clic' and sig and sig['tipo'] in ('esperarTexto', 'esperarSelector', 'esperarJs', 'esperarSinTexto'):
            clase, obj = 'reposo', REPOSO
        if obj is None:
            continue
        eventos.append((a['ini'], a['fin'], clase, obj))
    for e in mapa['esperas']:
        eventos.append((e['ini'], e['fin'], 'reposo', REPOSO))
    eventos.sort(key=lambda x: x[0])
    claves: list[list[float]] = []
    actual = REPOSO
    libre = 0.0           # no se mueve antes (ha de quedarse al menos 1,2 s)
    fin_ultimo = 0.0      # final de la última acción encuadrada

    def mover(t0: float, d: float, obj: tuple) -> None:
        nonlocal actual, libre
        t0 = max(t0, libre, claves[-1][1] if claves else 0.0)
        if t0 + d > limite:
            return
        claves.append([round(t0, 3), round(t0 + d, 3), *obj])
        actual = obj
        libre = t0 + d + 1.2

    for i, (ini, fin, clase, obj) in enumerate(eventos):
        if clase == 'reposo':
            if actual != REPOSO:
                mover(ini - 0.1, 0.6, REPOSO)
            continue
        if obj == REPOSO:
            if actual != REPOSO and ini - fin_ultimo > 0.8:
                mover(ini - 0.15, 0.6, REPOSO)
            continue
        if actual != REPOSO and en_centro(obj, actual):
            fin_ultimo = max(fin_ultimo, fin)
            continue
        # Si lo anterior acabó hace rato y esto no es inmediato, vuelve antes a reposo.
        if actual != REPOSO and ini - fin_ultimo > 2.6:
            mover(fin_ultimo + 0.6, 0.6, REPOSO)
        if clase == 'clic':
            d = min(0.9, max(0.6, fin - ini + 0.15))
            t0 = fin - d
        else:
            d = 0.8 if clase in ('resaltar', 'micro') else 0.7
            t0 = ini - 0.15
        if t0 < libre:
            # Aún no puede moverse: si la acción sigue después, llega tarde pero llega; si no, se queda donde está.
            if libre - t0 > 1.0:
                if fin > libre + 0.8:
                    t0 = libre
                else:
                    continue
        mover(t0, d, obj)
        fin_ultimo = max(fin_ultimo, fin)
    if actual != REPOSO:
        t0 = max(fin_ultimo + 0.8, libre)
        if resultado_ini is not None:
            t0 = min(t0, resultado_ini - 0.15)
        if fin_reposo is not None:
            t0 = min(t0, fin_reposo - 0.7)
        t0 = max(t0, claves[-1][1] if claves else 0)
        if t0 + 0.6 <= dur:
            claves.append([round(t0, 3), round(t0 + 0.6, 3), *REPOSO])
    return deriva(claves, limite, dur, volver=(resultado_ini is not None or fin_reposo is not None))


def deriva(claves: list[list[float]], limite: float, dur: float, volver: bool = False, minimo: float = 3.5,
           cuanto: float = 1.035) -> list[list[float]]:
    """En los planos que se quedan quietos más de `minimo` s, la cámara se acerca muy despacio (un 3,5 %): la regla de
    los 4 s de la guía (nunca más de 4 s sin cambio visual), sin rebotes ni saltos. Termina antes del movimiento siguiente,
    que sale del punto al que llegó."""
    out: list[list[float]] = []
    estado = REPOSO
    t = 0.0
    for k in claves + [None]:
        fin = (k[0] if k else min(limite, dur) - (0.7 if volver else 0)) - 0.1
        if fin - (t + 0.2) >= minimo:
            cx, cy, z = estado
            z2 = round(min(ZMAX + 0.05, z * cuanto), 3)
            cx2 = min(max(cx, W / 2 / z2), W - W / 2 / z2)
            cy2 = min(max(cy, H / 2 / z2), H - H / 2 / z2)
            out.append([round(t + 0.2, 3), round(fin, 3), round(cx2, 1), round(cy2, 1), z2])
            if not k and volver:  # antes del resultado o de un empuje, de vuelta a donde estaba
                out.append([round(fin + 0.1, 3), round(min(limite, dur), 3), *estado])
        if k:
            out.append(k)
            estado = (k[2], k[3], k[4])
            t = k[1]
    return out


# ---------------------------------------------------------------------------------------------- línea de tiempo
def catalogo_de(proyecto_path: Path) -> dict:
    """mapa, funcionalidades, criterios y cobertura: los del recorrido (el resumen no los repite)."""
    d = leer(proyecto_path)
    if 'mapa' not in d:
        d = {**leer(proyecto_path.parent / 'recorrido.json'), 'piezas': d['piezas']}
    return d


def voz_tarjeta(p: dict, voces: Path) -> list[dict]:
    frs = p.get('narracion') or []
    if not frs:
        return []
    idx = voces / f"{p['id']}.json"
    if not idx.exists():
        raise SystemExit(f"{p['id']}: falta la voz ({idx}); ejecuta voz.py narrar")
    d = leer(idx)
    if [f['texto'] for f in d['fragmentos']] != [f['texto'] for f in frs]:
        raise SystemExit(f"{p['id']}: la voz no coincide con la narración; ejecuta voz.py narrar")
    out, t = [], float(p.get('inicio_voz_s', 0.6))
    for fr, nr in zip(d['fragmentos'], frs):
        wav = fr['wav'] if Path(fr['wav']).exists() else str(voces / p['id'] / Path(fr['wav']).name)
        out.append({'n': fr['n'], 'ini': round(t, 3), 'fin': round(t + fr['duracion'], 3), 'wav': wav, 'texto': fr['texto'],
                    'microfono': False, 'criterio': nr.get('criterio')})
        t += fr['duracion'] + float(nr.get('tras') or 0.35)
    return out


def momento_palabra(voz: list[dict], palabra: str) -> float | None:
    """Segundo (en la pieza) en que la narración dice `palabra`, repartiendo por caracteres."""
    for v in voz:
        txt = sin_tildes(v['texto'])
        i = txt.find(sin_tildes(palabra))
        if i >= 0:
            return round(v['ini'] + (v['fin'] - v['ini']) * i / max(1, len(txt)), 3)
    return None


MINIMOS = {'portada': 7.4, 'problema': 8.0, 'reparto': 6.2, 'mapa': 2.5, 'mapa-inicio': 8.0, 'funcionalidad': 6.5,
           'criterios': 10.0, 'implantacion': 8.0, 'final': 13.0}
COLAS = {'portada': 1.0, 'problema': 0.6, 'reparto': 0.9, 'mapa': 1.0, 'mapa-inicio': 0.9, 'funcionalidad': 1.0,
         'criterios': 2.2, 'implantacion': 1.6, 'final': 4.6}
# Tarjeta de funcionalidad (guía, apartado 10, y revisión del 11/10): el texto completo está en pantalla desde ENTRA_F s
# hasta SALE_F s antes del final, y ese rato ha de durar al menos palabras / 3 + 1 s del «para qué sirve» (el titular lo
# dice la voz). En el resumen, con solo seis tarjetas, 7,5 s como mínimo.
ENTRA_F, SALE_F, MIN_F_RESUMEN = 1.1, 0.75, 7.5
# Panel de resultado: nunca antes del final de la última acción visible (clic, resaltado, tecleo, modal) + 0,3 s y al
# menos PANEL_MIN s en pantalla; si no cabe, la escena se alarga con el último fotograma (sin encoger el marco antes).
ACCIONES_VISIBLES = {'clic', 'clicTexto', 'resaltar', 'resaltarTexto', 'escribir', 'mantenerMicro', 'seleccionar', 'subir',
                     'scroll', 'tecla', 'hover', 'hoverTexto'}
PANEL_MIN = 2.8


def palabras(t: str) -> int:
    return len(re.findall(r'\w+', t or ''))


def lectura_s(t: str) -> float:
    """Tiempo mínimo de un texto en pantalla (guía, apartado 10): palabras / 3 + 1 s."""
    return palabras(t) / 3 + 1


def inicio_resultado(mapa: dict, dur: float) -> tuple[float | None, float]:
    """(inicio del panel de resultado, segundos que hay que alargar la escena con el último fotograma)."""
    r = mapa.get('resultado_ini')
    if r is None:
        return None, 0.0
    fin_acc = max([a['fin'] for a in mapa['acciones'] if a.get('visible') and a['tipo'] in ACCIONES_VISIBLES and a['ini'] < dur],
                  default=0.0)
    r2 = round(max(r, fin_acc + 0.3), 3)
    return r2, round(max(0.0, r2 + PANEL_MIN - dur), 3)


def construir_linea(a: argparse.Namespace) -> dict:
    proy_path = Path(a.proyecto).resolve()
    proyecto, piezas = cargar_proyecto(proy_path)
    cat = catalogo_de(proy_path)
    funcs = {f['id']: f for f in cat.get('funcionalidades', [])}
    bloques_mapa = {b['id']: b for b in cat['mapa']['bloques']}
    trab = Path(a.trabajo).resolve()
    escenas = trab / 'escenas'
    voces = Path(a.voces).resolve()
    resumen = 'mapa' not in leer(proy_path)

    # Funcionalidades que salen en este vídeo, en orden, y su bloque.
    tarjetas_f = [p for p in piezas if p.get('pieza') == 'funcionalidad']
    orden_f = [p['funcionalidad'] for p in tarjetas_f]
    num_f = {fid: i + 1 for i, fid in enumerate(orden_f)}
    bloques_video = []
    for p in tarjetas_f:
        if p['bloque'] not in bloques_video:
            bloques_video.append(p['bloque'])

    items: list[dict] = []
    # Apertura (6 s, sin voz): tres momentos reales.
    if piezas and piezas[0].get('pieza') == 'portada':
        items.append({'id': 'apertura', 'tipo': 'apertura', 'pieza': 'apertura', 'capitulo': piezas[0].get('capitulo')})
    for p in piezas:
        if p['tipo'] == 'escena':
            m = leer(escenas / f"{p['id']}.mapa.json")
            items.append({'id': p['id'], 'tipo': 'escena', 'pieza': 'escena', 'p': p, 'mapa': m, 'capitulo': p.get('capitulo'),
                          'funcionalidad': p.get('funcionalidad')})
        else:
            items.append({'id': p['id'], 'tipo': p['pieza'], 'pieza': p['pieza'], 'p': p, 'capitulo': p.get('capitulo'),
                          'funcionalidad': p.get('funcionalidad')})

    # Duraciones y voz de cada pieza.
    for it in items:
        if it['tipo'] == 'apertura':
            it['dur'] = 6.0
            it['voz'] = []
        elif it['tipo'] == 'escena':
            it['dur'] = fot(it['mapa']['duracion'])
            it['voz'] = [v for v in it['mapa']['voz'] if v['ini'] < it['dur']]
            r = it['p'].get('resultado')
            if isinstance(r, dict):
                r0, ext = inicio_resultado(it['mapa'], it['dur'])
                if r0 is not None and r0 < it['dur'] + ext - 1.2:
                    it['res_ini'] = r0
                    if ext > 0:
                        it['extension'] = math.ceil(ext * FPS) / FPS
                        it['dur'] = round(it['dur'] + it['extension'], 4)
        else:
            p = it['p']
            it['voz'] = voz_tarjeta(p, voces)
            fin_voz = max([v['fin'] for v in it['voz']], default=0.0)
            clave = 'mapa-inicio' if (p['pieza'] == 'mapa' and not p.get('destacar')) else p['pieza']
            minimo = MINIMOS.get(clave, 4.0)
            if clave == 'funcionalidad':
                minimo = max(MIN_F_RESUMEN if resumen else minimo, ENTRA_F + lectura_s(p.get('para_que', '')) + SALE_F)
            it['dur'] = math.ceil(max(minimo, fin_voz + COLAS.get(clave, 1.0)) * FPS) / FPS

    # Bloques de render.
    bloque = 'inicio'
    for it in items:
        p = it.get('p') or {}
        if it['tipo'] in ('criterios', 'implantacion', 'final'):
            bloque = 'cierre'
        elif it['tipo'] == 'mapa' and p.get('destacar'):
            bloque = p['destacar']
        elif resumen and it['tipo'] == 'funcionalidad':
            bloque = p['bloque']
        it['bloque'] = bloque

    # Transiciones según el tipo de corte (guía, apartado 7).
    for i, it in enumerate(items):
        prev = items[i - 1] if i else None
        sig = items[i + 1] if i + 1 < len(items) else None
        if it['tipo'] == 'escena':
            if prev and prev['tipo'] == 'funcionalidad':
                it['entrada'] = 'zoom'
            elif prev and prev['tipo'] == 'escena':
                mismo = (quien_es(prev['p']) == quien_es(it['p']))
                it['entrada'] = 'corte' if mismo else 'empuje'
            elif prev and prev['tipo'] in ('mapa', 'reparto', 'problema', 'portada'):
                it['entrada'] = 'aparece' if prev['tipo'] != 'mapa' else 'cortinilla'
            else:
                it['entrada'] = 'cortinilla'
            if sig and sig['tipo'] == 'escena':
                it['salida'] = 'corte' if quien_es(sig['p']) == quien_es(it['p']) else 'empuje'
            elif sig:
                it['salida'] = 'cortinilla'
            else:
                it['salida'] = 'nada'
        else:
            it['entrada'] = 'cortinilla' if (prev and prev['tipo'] == 'escena') else ('continua' if (prev and prev['tipo'] == 'mapa' and it['tipo'] == 'mapa') else 'sucesion')
            if sig is None:
                it['salida'] = 'negro'
            elif it['tipo'] == 'funcionalidad':
                it['salida'] = 'zoom'
            elif it['tipo'] == 'mapa' and sig['tipo'] == 'mapa':
                it['salida'] = 'continua'
            else:
                it['salida'] = 'texto'

    # Tiempos globales.
    t = 0.0
    for it in items:
        it['ini'] = round(t, 4)
        t += it['dur']
    total = round(t, 4)

    # Bloques: inicio y fin; cortinillas (en el instante en que tapa todo).
    nombres_b = []
    for it in items:
        if it['bloque'] not in nombres_b:
            nombres_b.append(it['bloque'])
    bloques = []
    for b in nombres_b:
        its = [x for x in items if x['bloque'] == b]
        bloques.append({'id': b, 'ini': its[0]['ini'], 'fin': round(its[-1]['ini'] + its[-1]['dur'], 4)})
    cortinillas = [it['ini'] for it in items if it['entrada'] == 'cortinilla']

    # Raíl de bloques del mapa (los del ciclo y los de alrededor) con su duración real.
    rail_b = [b for b in bloques if b['id'] in bloques_mapa]
    n_rail = len(rail_b)
    total_rail = sum(b['fin'] - b['ini'] for b in rail_b) or 1
    hueco = 6
    ancho_util = 1560 - hueco * max(0, n_rail - 1)
    x = 0.0
    rail = []
    for k, b in enumerate(rail_b):
        w = ancho_util * (b['fin'] - b['ini']) / total_rail
        verbo = bloques_mapa[b['id']]['verbo']
        rail.append({'id': b['id'], 'ini': b['ini'], 'fin': b['fin'], 'x': round(x, 1), 'w': round(w, 1),
                     'etiqueta': f'{k + 1:02d}/{n_rail:02d} {verbo}'})
        x += w + hueco

    linea = {'proyecto': str(proy_path), 'titulo': proyecto.get('titulo'), 'resumen': resumen, 'duracion': total, 'items': items,
             'bloques': bloques, 'cortinillas': cortinillas, 'rail': rail, 'num_f': num_f, 'orden_f': orden_f,
             'bloques_video': bloques_video, 'funcs': funcs, 'mapa_bloques': bloques_mapa, 'catalogo': {
                 k: cat.get(k) for k in ('criterios', 'cobertura_bases')}}
    return linea


# ---------------------------------------------------------------------------------------------- subtítulos
def subtitulos(linea: dict) -> list[dict]:
    cues = []
    for it in linea['items']:
        p = it.get('p') or {}
        for v in it['voz']:
            g0, g1 = it['ini'] + v['ini'], it['ini'] + v['fin']
            if v.get('microfono'):
                texto = p.get('texto_microfono') or ''
                if not texto:
                    continue
                quien = (PERSONAS.get(quien_es(p), ('', ''))[0].split() or [''])[0]
                cues.append({'tipo': 'micro', 'ini': g0, 'fin': g1, 'texto': texto, 'wav': v['wav'], 'quien': f'{quien}, por voz'})
                continue
            trozos = montaje.trocear_subtitulo(v['texto'], 84)
            pesos = [len(z) for z in trozos]
            acum = 0
            for z, w in zip(trozos, pesos):
                a0 = g0 + (g1 - g0) * acum / sum(pesos)
                acum += w
                a1 = g0 + (g1 - g0) * acum / sum(pesos)
                cues.append({'tipo': 'narrador', 'ini': a0, 'fin': a1, 'texto': z})
    cues.sort(key=lambda c: c['ini'])
    # Sin solaparse; al menos 1,2 s y como mucho 17 caracteres por segundo (guía, apartado 12): si el hueco hasta el
    # siguiente lo permite, la placa se queda más tiempo que la voz.
    for k, c in enumerate(cues):
        fin = max(c['fin'], c['ini'] + 1.2, c['ini'] + len(c['texto']) / 16.5)
        if k + 1 < len(cues):
            fin = min(fin, max(c['fin'], cues[k + 1]['ini'] - 0.05))
        c['fin'] = round(fin, 3)
        c['ini'] = round(c['ini'], 3)
    # Palabra a palabra para lo que se dice al micrófono: la voz útil del WAV, repartida por letras.
    for c in cues:
        if c['tipo'] != 'micro':
            continue
        x = montaje.leer_wav(Path(c['wav']))
        blq = TASA // 100
        e = np.sqrt(np.mean(x[:len(x) // blq * blq].reshape(-1, blq) ** 2, axis=1))
        on = np.where(e > 0.1 * e.max())[0]
        v0, v1 = (on[0] / 100, on[-1] / 100) if len(on) else (0.0, len(x) / TASA)
        pals = c['texto'].split()
        pesos = [len(re.sub(r'[^\wáéíóúñü]', '', w, flags=re.I)) + 1 for w in pals]
        # Las líneas se fijan desde la primera palabra (cortes equilibrados), para que la placa no cambie de forma.
        lineas = partir(c['texto'], fuente_pil('fira', 38, 600), 1020, 2)
        cortes, n = set(), 0
        for ln in lineas[:-1]:
            n += len(ln.split())
            cortes.add(n)
        acum, pal = 0, []
        for k, (w, pz) in enumerate(zip(pals, pesos)):
            pal.append({'w': html.escape(w), 't': round(c['ini'] + v0 + (v1 - v0) * acum / sum(pesos), 3), 'br': (k + 1) in cortes})
            acum += pz
        c['palabras'] = pal
    return cues


def srt(cues: list[dict], destino: Path) -> None:
    def ts(s):
        ms = int(round(s * 1000))
        return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}'
    out = []
    for i, c in enumerate(cues, 1):
        z = f"«{c['texto']}»" if c['tipo'] == 'micro' else c['texto']
        out.append(f"{i}\n{ts(c['ini'])} --> {ts(c['fin'])}\n{montaje.partir_lineas(z)}\n")
    destino.write_text('\n'.join(out) + '\n', encoding='utf-8')


# ---------------------------------------------------------------------------------------------- medios
def foto(video: Path, t: float, destino: Path, caja: list | None = None, ancho: int | None = None) -> str:
    """Fotograma de un vídeo limpio en PNG (con la conversión de color correcta), recortado o reducido."""
    if not destino.exists():
        vf = []
        if caja:
            x, y, w, h = [int(round(v)) for v in caja]
            vf.append(f'crop={w}:{h}:{x}:{y}')
        if ancho:
            vf.append(f'scale={ancho}:-2:flags=lanczos')
        vf.append('scale=in_color_matrix=bt709:in_range=tv:out_range=pc,format=rgb24')
        destino.parent.mkdir(parents=True, exist_ok=True)
        for atras in (0.0, 0.15, 0.4, 1.0):  # el último fotograma a veces no se alcanza buscando: un poco antes
            correr([ffmpeg(), '-v', 'error', '-y', '-ss', f'{max(0.0, t - atras):.3f}', '-i', str(video), '-frames:v', '1',
                    '-vf', ','.join(vf), str(destino)])
            if destino.exists():
                break
        if not destino.exists():
            raise SystemExit(f'No sale el fotograma {t:.2f} s de {video.name}')
    return destino.name


def fondo_png(destino: Path) -> None:
    """Fondo de marca (guía, apartado 4): degradado radial, cuadrícula técnica que se apaga hacia los bordes y grano."""
    if destino.exists():
        return
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - 0.42 * W) / W) ** 2 + ((yy - 0.30 * H) / H) ** 2) / 0.85
    d = np.clip(d, 0, 1) ** 1.2
    c0, c1 = np.array([0x27, 0x2C, 0x33], np.float32), np.array([0x18, 0x1B, 0x1F], np.float32)
    img = c0[None, None, :] * (1 - d[..., None]) + c1[None, None, :] * d[..., None]
    rejilla = np.zeros((H, W), np.float32)
    rejilla[:, ::48] = 0.022
    rejilla[::48, :] = 0.022
    rejilla[:, ::192] = 0.03
    rejilla[::192, :] = 0.03
    borde = 1 - np.clip(np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) - 0.35, 0, 1) / 0.65
    img = img + (255 - img) * (rejilla * np.clip(borde, 0, 1))[..., None]
    img = img + np.random.default_rng(3).normal(0, 1.6, img.shape).astype(np.float32)
    Image.fromarray(np.clip(img + 0.5, 0, 255).astype(np.uint8)).save(destino)


def enlazar(origen: Path, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        if destino.stat().st_size == origen.stat().st_size and destino.stat().st_mtime >= origen.stat().st_mtime:
            return
        destino.unlink()
    try:
        os.link(origen, destino)
    except OSError:
        shutil.copy2(origen, destino)


def desplazamiento(video: Path, t0: float, t1: float, total: float) -> list[tuple[float, float]]:
    """Desplazamiento vertical de la página (px del vídeo) en cada fotograma entre t0 y t1, medido con el perfil de filas
    de la zona de contenido (sin la barra lateral) frente al primer fotograma. `total` es el desplazamiento esperado (con
    su signo); se busca entre 0 y ese valor."""
    x0, x1 = 360, 1860
    r = subprocess.run([ffmpeg(), '-v', 'error', '-ss', f'{max(0, t0):.3f}', '-i', str(video), '-t', f'{t1 - t0:.3f}',
                        '-vf', f'crop={x1 - x0}:1080:{x0}:0,format=gray', '-f', 'rawvideo', '-'], capture_output=True)
    f = np.frombuffer(r.stdout, np.uint8)
    n = len(f) // ((x1 - x0) * 1080)
    if n < 2:
        return [(t0, 0.0), (t1, total)]
    perf = f[:n * (x1 - x0) * 1080].reshape(n, 1080, x1 - x0).astype(np.float32).mean(axis=2)
    ref = perf[0]
    signo = -1 if total < 0 else 1
    maximo = int(abs(total)) + 40
    out = []
    for k in range(n):
        mejor, md = 0, 1e18
        for d in range(0, maximo + 1, 1):
            s = signo * d
            # fila y del fotograma k corresponde a la fila y - s del de referencia (s negativo: el contenido sube)
            if s <= 0:
                a, b = perf[k][:1080 + s], ref[-s:]
            else:
                a, b = perf[k][s:], ref[:1080 - s]
            if len(a) < 300:
                break
            a = (a - a.mean()) / (a.std() + 1e-6)  # sin depender del velo oscuro de los resaltados
            b = (b - b.mean()) / (b.std() + 1e-6)
            e = float(np.mean((a - b) ** 2))
            if e < md:
                md, mejor = e, s
        out.append((t0 + k / FPS, float(mejor)))
    # El desplazamiento va en un solo sentido y no pasa del total: se corrigen las lecturas sueltas.
    limpio, extremo = [], 0.0
    for t, d in out:
        d = max(d, total) if signo < 0 else min(d, total)
        extremo = min(extremo, d) if signo < 0 else max(extremo, d)
        limpio.append((t, extremo))
    return limpio


def tramos_tapas(video: Path, mapa: dict, tapas: list[dict], dur: float) -> tuple[list[dict], list[list[float]]]:
    """Las tapas de una escena (v2.tapas: texto y dos posiciones, al principio y al final de un desplazamiento de la
    página) como (etiquetas, rectángulos que se pixelan en el vídeo).

    Las etiquetas son fijas: una antes del desplazamiento y otra después, del mismo tamaño. Mientras la página se mueve
    (medido fotograma a fotograma) no hay etiqueta: toda la franja de las columnas tapadas va pixelada en el propio vídeo,
    así que nada se lee aunque la medida vaya un fotograma tarde y la tapa nunca se deforma (revisión del 11/10). Debajo
    de cada etiqueta el vídeo también va pixelado: si la etiqueta se corriera un píxel, tampoco asomaría nada."""
    etiquetas, rects = [], []
    retraso = -ADELANTO_HF  # HyperFrames enseña cada fotograma de un vídeo unos dos fotogramas tarde
    por_accion: dict[int, list[dict]] = {}
    for tp in tapas:
        por_accion.setdefault(tp['posiciones'][0][0], []).append(tp)
    for i, grupo in por_accion.items():
        a = next(x for x in mapa['acciones'] if x['i'] == i)
        if a['tipo'] != 'scroll':
            for tp in grupo:
                for (_, momento, x, y, w, h) in tp['posiciones'][:1]:
                    etiquetas.append({'texto': html.escape(tp['texto']), 'tramos': [[0.0, dur, x, y, w, h]]})
                    rects.append([x - 4, y - 4, w + 8, h + 8, 0.0, dur])
            continue
        (_, _, x0, y0, w0, h0), (_, _, _, y1, _, _) = grupo[0]['posiciones']
        medidas = desplazamiento(video, a['ini'] - 0.1, a['fin'] + 0.6, y1 - y0)
        mov = [t for (t, dy), (_, dy2) in zip(medidas, medidas[1:]) if dy2 != dy]
        s0 = (mov[0] if mov else a['ini']) - 0.1
        s1 = (mov[-1] + 1 / FPS if mov else a['fin']) + 0.15
        xs = [tp['posiciones'][0][2] for tp in grupo]
        xe = [tp['posiciones'][0][2] + tp['posiciones'][0][4] for tp in grupo]
        rects.append([min(xs) - 8, 0, max(xe) - min(xs) + 16, 1080, round(s0, 3), round(s1, 3)])
        for tp in grupo:
            (_, _, x, ya, w, h), (_, _, _, yb, _, _) = tp['posiciones']
            etiquetas.append({'texto': html.escape(tp['texto']),
                              'tramos': [[0.0, round(s0 + retraso, 3), x, ya, w, h], [round(s1 + retraso, 3), dur, x, yb, w, h]]})
            rects.append([x - 4, ya - 4, w + 8, h + 8, 0.0, round(s0 + 0.04, 3)])
            rects.append([x - 4, yb - 4, w + 8, h + 8, round(s1 - 0.04, 3), dur])
    return etiquetas, rects


def procesar_escena(limpio: Path, destino: Path, mapa: dict, v2: dict, extension: float, dur: float) -> Path:
    """El vídeo de la escena que usa el montaje: el limpio con, si los pide la escena (v2), los nombres tapados
    (pixelados), los ratos congelados (v2.congelar: un rato que se ve mal, como una página cargando, se sustituye por el
    fotograma de antes), los recortes borrados (v2.borrar: un dato que contradice el orden del guion, pintado con el
    color del fondo), los parches (v2.parches: una nota del grabador que tapa lo que demuestra la escena se cubre con
    ese trozo de un fotograma anterior, con el mismo velo del resaltado) y el último fotograma alargado `extension` s
    (para que el panel de resultado no tape una acción). Sin nada de eso, el limpio tal cual. Se rehace solo si cambia
    su firma."""
    tapas, congelar, borrar = v2.get('tapas') or [], v2.get('congelar') or [], v2.get('borrar') or []
    parches = v2.get('parches') or []
    if not (tapas or congelar or borrar or parches or extension > 0):
        return limpio
    firma = json.dumps({'v': 3, 'limpio': [limpio.stat().st_size, int(limpio.stat().st_mtime)], 'tapas': tapas, 'congelar': congelar,
                        'borrar': borrar, 'ext': extension, **({'parches': parches} if parches else {})},
                       sort_keys=True, ensure_ascii=False)
    ff = destino.with_suffix('.firma')
    if destino.exists() and ff.exists() and ff.read_text(encoding='utf-8') == firma:
        return destino
    filtros, cur, k = [], '0:v', 0
    entradas = ['-i', str(limpio)]
    n_fot = int(round(mapa['duracion'] * FPS))
    for c in congelar:
        t0 = t_accion(mapa, c['accion'], c.get('momento', 'fin'), float(c.get('desde', 0)))
        t1 = t_accion(mapa, c['accion'], c.get('momento', 'fin'), float(c.get('hasta', 0)))
        f0, f1 = max(1, int(round(t0 * FPS))), min(n_fot - 1, int(round(t1 * FPS)))
        filtros.append(f'[{cur}]split[c{k}a][c{k}b];[c{k}a][c{k}b]freezeframes=first={f0}:last={f1}:replace={f0 - 1}[c{k}]')
        cur, k = f'c{k}', k + 1
    for b in borrar:
        x, y, w, h = [int(round(v)) for v in b['caja']]
        if b.get('copiar_de'):
            # Se tapa con un trozo vacío de la misma página (del mismo fotograma): así sigue el velo de los resaltados.
            cx, cy = [int(round(v)) for v in b['copiar_de']]
            filtros.append(f'[{cur}]split[b{k}a][b{k}b];[b{k}b]crop={w}:{h}:{cx}:{cy}[b{k}p];[b{k}a][b{k}p]overlay={x}:{y}[b{k}]')
        else:
            color = b.get('color', '#FFFFFF').lstrip('#')
            filtros.append(f'[{cur}]drawbox=x={x}:y={y}:w={w}:h={h}:color=0x{color}@1:t=fill[b{k}]')
        cur, k = f'b{k}', k + 1
    for n_p, pa in enumerate(parches):
        # El trozo sale del limpio en `fuente` (sin velo ni nota) y se pone entre `desde` y `hasta`: tal cual y, encima,
        # con el velo del grabador (rgba(18,21,25,.36)), que entra en `rampa` s como el de la página. Después, una sola
        # máscara con los bordes difuminados `difuminar` px (menos los que tocan el borde del vídeo), para que no se
        # note el corte en el halo del resaltado ni en la sombra de la nota.
        x, y, w, h = [int(round(v)) // 2 * 2 for v in pa['caja']]
        t_f = t_accion(mapa, pa['accion'], *pa['fuente'])
        a0 = t_accion(mapa, pa['accion'], *pa['desde'])
        a1 = t_accion(mapa, pa['accion'], *pa['hasta'])
        png = destino.with_name(f'{destino.stem}.parche{n_p}.png')
        mascara = destino.with_name(f'{destino.stem}.parche{n_p}.mascara.png')
        png.unlink(missing_ok=True)
        foto(limpio, t_f, png, [x, y, w, h])
        borde = max(1, int(pa.get('difuminar', 8)))
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        dist = np.full((h, w), float(borde), np.float32)
        for lado, toca in ((xx, x <= 0), (w - 1 - xx, x + w >= W), (yy, y <= 0), (h - 1 - yy, y + h >= H)):
            if not toca:
                dist = np.minimum(dist, lado)
        Image.fromarray((np.clip(dist / borde, 0, 1) * 255 + 0.5).astype(np.uint8), 'L').save(mascara)
        larga = ['-loop', '1', '-framerate', str(FPS), '-t', f'{mapa["duracion"] + extension:.3f}']
        e = sum(1 for z in entradas if z == '-i')  # índice de la entrada del trozo; la máscara, la siguiente
        entradas += [*larga, '-i', str(png), *larga, '-i', str(mascara)]
        color = pa.get('color_velo', '#121519').lstrip('#')
        velo, rampa = float(pa.get('velo', 0.36)), max(1 / FPS, float(pa.get('rampa', 0.2)))
        filtros.append(f"[{e}:v]scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p,split[p{k}u][p{k}w];"
                       f"[p{k}w]drawbox=x=0:y=0:w=iw:h=ih:color=0x{color}@{velo:.3f}:t=fill,format=yuva420p,"
                       f"fade=t=in:st={a0:.3f}:d={rampa:.3f}:alpha=1[p{k}v];"
                       f"[p{k}u][p{k}v]overlay=0:0:format=yuv420[p{k}o];[{e + 1}:v]format=gray[p{k}m];"
                       f"[p{k}o][p{k}m]alphamerge[p{k}p];"
                       f"[{cur}][p{k}p]overlay={x}:{y}:enable='between(t,{a0:.3f},{a1:.3f})'[p{k}]")
        cur, k = f'p{k}', k + 1
    if tapas:
        _, rects = tramos_tapas(limpio, mapa, tapas, dur)
        for (x, y, w, h, a, b) in rects:
            x0, y0 = max(0, int(x)), max(0, int(y))
            x1, y1 = min(1920, int(x + w)), min(1080, int(y + h))
            x, y, w, h = x0, y0, x1 - x0, y1 - y0
            if w < 8 or h < 8:
                continue
            bw, bh = max(2, w // 14), max(2, h // 14)
            filtros.append(f'[{cur}]split[t{k}a][t{k}b];[t{k}b]crop={w}:{h}:{x}:{y},scale={bw}:{bh}:flags=area,'
                           f'scale={w}:{h}:flags=neighbor,gblur=sigma=2.5[t{k}p];'
                           f"[t{k}a][t{k}p]overlay={x}:{y}:enable='between(t,{a:.3f},{b:.3f})'[t{k}]")
            cur, k = f't{k}', k + 1
    if extension > 0:
        filtros.append(f'[{cur}]tpad=stop_mode=clone:stop_duration={extension:.3f}[e{k}]')
        cur, k = f'e{k}', k + 1
    filtros.append(f'[{cur}]fps={FPS},format=yuv420p[v]')
    tmp = destino.with_name(destino.stem + '.tmp.mp4')
    correr([ffmpeg(), '-y', '-hide_banner', '-loglevel', 'error', *entradas, '-filter_complex', ';'.join(filtros),
            '-map', '[v]', '-an', '-c:v', 'h264_nvenc', '-preset', 'p7', '-rc', 'vbr', '-cq', '16', '-b:v', '20M', '-maxrate', '40M',
            '-g', '15', '-r', str(FPS), '-t', f'{mapa["duracion"] + extension:.3f}', '-color_range', 'tv', '-colorspace', 'bt709',
            '-color_primaries', 'bt709', '-color_trc', 'bt709', '-movflags', '+faststart', str(tmp)])
    tmp.replace(destino)
    ff.write_text(firma, encoding='utf-8')
    return destino


# ---------------------------------------------------------------------------------------------- composición
def t_accion(mapa: dict, i: int, momento: str, desfase: float = 0.0) -> float:
    a = next(x for x in mapa['acciones'] if x['i'] == i)
    t = {'ini': a['ini'], 'fin': a['fin'], 'mitad': (a['ini'] + a['fin']) / 2}[momento]
    return t + desfase


def video_tag(vid: str, src: str, ini: float, dur: float, desde: float = 0.0) -> str:
    return (f'<video id="{vid}" class="clip" src="{src}" data-start="{ini:.4f}" data-duration="{dur:.4f}" '
            f'data-media-start="{desde:.4f}" muted playsinline></video>')


class Compositor:
    def __init__(self, linea: dict, trab: Path):
        self.L = linea
        self.trab = trab
        self.hf = trab / 'hf'
        self.comun = self.hf / 'comun'       # fotos y fondo comunes; cada bloque los enlaza (enlaces duros)
        self.necesarios: dict[str, Path] = {}
        self.escenas = trab / 'escenas'
        self.items = linea['items']
        self.por_id = {it['id']: it for it in self.items}

    # -- utilidades
    def escena_externa(self, sid: str) -> tuple[Path, dict, dict] | None:
        """Una escena que no está en este vídeo (el resumen usa algunas del recorrido para las pruebas de los criterios):
        su carpeta de escenas limpias, su mapa y su pieza."""
        if not hasattr(self, '_externas'):
            self._externas = {}
            rec = Path(self.L['proyecto']).with_name('recorrido.json')
            dir_rec = self.trab.parent / 'recorrido' / 'escenas'
            if rec.exists() and dir_rec.exists() and Path(self.L['proyecto']).name != 'recorrido.json':
                _, piezas = cargar_proyecto(rec)
                for p in piezas:
                    if p['tipo'] == 'escena' and (dir_rec / f"{p['id']}.mapa.json").exists():
                        self._externas[p['id']] = (dir_rec, leer(dir_rec / f"{p['id']}.mapa.json"), p)
        return self._externas.get(sid)

    def existe(self, sid: str) -> bool:
        return sid in self.por_id or self.escena_externa(sid) is not None

    def mapa_de(self, sid: str) -> dict:
        return self.por_id[sid]['mapa'] if sid in self.por_id else self.escena_externa(sid)[1]

    def fuente(self, sid: str) -> Path:
        """El vídeo de la escena ya procesado (tapas, congelados, borrados y el final alargado), creado si hace falta."""
        if not hasattr(self, '_fuentes'):
            self._fuentes = {}
        if sid not in self._fuentes:
            if sid in self.por_id:
                it = self.por_id[sid]
                carpeta, mapa, p, ext, dur = self.escenas, it['mapa'], it['p'], float(it.get('extension') or 0), it['dur']
                destino = carpeta / f'{sid}.final.mp4'
            else:
                carpeta, mapa, p = self.escena_externa(sid)
                ext, dur = 0.0, mapa['duracion']
                destino = carpeta / f'{sid}.final-externa.mp4'  # sin alargar: no pisa la del recorrido
            self._fuentes[sid] = procesar_escena(carpeta / f'{sid}.mp4', destino, mapa, p.get('v2') or {}, ext, dur)
        return self._fuentes[sid]

    def video_escena(self, sid: str) -> str:
        rel = f'media/escenas/{sid}.mp4'
        self.necesarios[rel] = self.fuente(sid)
        return rel

    def foto(self, sid: str, t: float, nombre: str, caja=None, ancho=None) -> str:
        n = foto(self.fuente(sid), t, self.comun / 'fotos' / f'{nombre}.png', caja, ancho)
        rel = f'media/fotos/{n}'
        self.necesarios[rel] = self.comun / 'fotos' / n
        return rel

    def escena_de_funcionalidad(self, fid: str, ultima: bool) -> dict | None:
        es = [it for it in self.items if it['tipo'] == 'escena' and it.get('funcionalidad') == fid]
        return (es[-1] if ultima else es[0]) if es else None

    # -- piezas
    def escena(self, it: dict, b0: float) -> tuple[dict, str]:
        m, p = it['mapa'], it['p']
        sid = it['id']
        L = self.L
        ini = it['ini'] - b0
        fid = p.get('funcionalidad')
        f = L['funcs'].get(fid) if fid else None
        res = None
        r = p.get('resultado')
        if isinstance(r, dict) and it.get('res_ini') is not None:
            res = {'ini': it['res_ini'], 'texto': html.escape(r['texto']), 'bases': [chip_base(b) for b in r['bases']]}
            v2 = p.get('v2') or {}
            if v2.get('comparar'):
                c = v2['comparar']
                res['comparar'] = {'lado_a_lado': bool(c.get('lado_a_lado'))}
                for lado in ('antes', 'despues'):
                    x = c[lado]
                    t = t_accion(m, x['accion'], x.get('momento', 'fin'), float(x.get('desfase', 0)))
                    res['comparar'][lado] = {'img': self.foto(sid, t, f'{sid}-{lado}', x['caja']), 'etiqueta': html.escape(x['etiqueta']),
                                             'tono': x.get('tono', 'neutro')}
            if v2.get('iluo'):
                res['iluo'] = v2['iluo']
        fin_reposo = it['dur'] if it['salida'] == 'empuje' else None
        cam = camara(m, fin_reposo, res['ini'] if res else None)
        esperas = [{**{k: e[k] for k in ('ini', 'fin', 'factor', 'real', 'rampa')}, 'tarea': html.escape(tarea_corta(e['etiqueta']))}
                   for e in m['esperas'] if e['fin'] - e['ini'] >= 0.35]
        seccion = f['nombre'] if f else (p.get('cabecera') or 'Metalúrgica Arlanza · empresa ficticia')
        cab = {'numero': L['num_f'].get(fid), 'seccion': html.escape(seccion),
               'persona': persona_de(quien_es(p)),
               'bases_n': len((f or {}).get('bases') or []),
               'entra': it['entrada'] in ('zoom', 'cortinilla', 'aparece')}
        previo_html = ''
        k = self.items.index(it)
        if it['entrada'] == 'empuje':
            prev = self.items[k - 1]
            cab['persona_previa'] = persona_de(quien_es(prev['p']))
            img = self.foto(prev['id'], prev['dur'] - 1 / FPS, f"{prev['id']}-ultimo")
            previo_html = f'<div class="marco-previo"><img src="{img}"></div>'
        tp_v2 = (p.get('v2') or {}).get('tapas', [])
        tapas = tramos_tapas(self.escenas / f'{sid}.mp4', m, tp_v2, it['dur'])[0] if tp_v2 else []
        llamadas = []
        for ll in (p.get('v2') or {}).get('llamadas', []):
            a = next((x for x in m['acciones'] if x['i'] == ll['accion']), None)
            if a is None or a['ini'] >= it['dur']:  # una toma recortada (hasta_accion) puede no llegar a esa acción
                continue
            el = a.get('elemento')
            if el and a.get('visible'):
                # Mientras dura el resaltado (al menos 1,6 s o «min», y 2,8 s o «dur» como mucho) y nunca encima del panel
                # de resultado.
                l0 = a['ini'] + ll.get('desfase', 0.35)
                l1 = min(max(a['fin'], l0 + max(1.6, float(ll.get('min', 0)))), l0 + ll.get('dur', 2.8),
                         (res['ini'] - 0.2) if res else it['dur'] - 0.4)
                if l1 - l0 >= 1.2:
                    llamadas.append({'ini': round(l0, 3), 'fin': round(l1, 3), 'texto': html.escape(ll['texto']),
                                     'caja': [el['x'], el['y'], el['w'], el['h']]})
        src = self.video_escena(sid)
        html_p = (f'<div class="pieza escena" id="p-{sid}">{previo_html}<div class="marco"><div class="camara">'
                  f'{video_tag("v-" + sid, src, ini, it["dur"])}</div><div class="barra-real"></div></div></div>')
        datos = {'id': sid, 'tipo': 'escena', 'ini': round(ini, 4), 'dur': it['dur'], 'entrada': it['entrada'], 'salida': it['salida'],
                 'camara': cam, 'esperas': esperas, 'resultado': res, 'cabecera': cab, 'llamadas': llamadas, 'tapas': tapas}
        it['_camara'] = cam
        return datos, html_p

    def funcionalidad(self, it: dict, b0: float) -> tuple[dict, str]:
        p = it['p']
        L = self.L
        fid = p['funcionalidad']
        n = L['num_f'][fid]
        total = len(L['orden_f'])
        verbo = L['mapa_bloques'][p['bloque']]['verbo']
        primera = self.escena_de_funcionalidad(fid, False)
        ultima = self.escena_de_funcionalidad(fid, True)
        ini = it['ini'] - b0
        pv = {'x': 980, 'y': 0, 'w': 820, 'h': 461}
        # Columna izquierda: altura aproximada para centrarla en la zona útil.
        lineas = partir(p['nombre'], fuente_pil('archivo', 64, 800, 100), 780)
        f_txt = fuente_pil('fira', 32, 400)
        n_pq = len(partir(p['para_que'], f_txt, 780, 6))
        alto = 26 + 22 + 72 * len(lineas) + 34 + 24 + 10 + 44 * n_pq + 30 + 46 + 16 + 50 * math.ceil(len(p['bases']) / 2)
        y0 = int(max(110, 90 + (860 - alto) / 2))
        pv['y'] = int(max(170, min(y0 + 30, 300)))
        persona_txt = p.get('persona', '')
        avatares = []
        for u, (nom, _) in PERSONAS.items():
            clave = nom if u != 'admin' else 'administración'
            if clave.lower() in persona_txt.lower():
                avatares.append((persona_txt.lower().index(clave.lower()), persona_de(u)))
        avatares = [a for _, a in sorted(avatares, key=lambda x: x[0])] or [persona_de(None)]
        per = {'avatares': avatares, 'texto': html.escape(persona_txt)}
        # Raya de funcionalidades: una marca por funcionalidad, con más aire entre bloques.
        raya, xr = [], 0.0
        gaps = sum(1 for i in range(1, total) if L['funcs'][L['orden_f'][i]].get('bloque') != L['funcs'][L['orden_f'][i - 1]].get('bloque'))
        ancho = (1680 - 4 * (total - 1 - gaps) - 16 * gaps) / total
        for i, fx in enumerate(L['orden_f']):
            if i:
                xr += 16 if L['funcs'][fx].get('bloque') != L['funcs'][L['orden_f'][i - 1]].get('bloque') else 4
            raya.append({'x': round(xr, 1), 'w': round(ancho, 1), 'estado': 'hecho' if i + 1 < n else ('actual' if i + 1 == n else '')})
            xr += ancho
        # Vista previa: el resultado de la última escena; al final, la primera imagen de la primera escena.
        prev_html = ''
        # La vista previa es el resultado de la última escena; si esa lleva tapas (Sistema, en el registro) y hay otra,
        # mejor la otra: lo primero que se ve (revisión del 11/10).
        if ultima and primera and ultima is not primera and (ultima['p'].get('v2') or {}).get('tapas'):
            ultima = primera
        if ultima and primera:
            ru = ultima.get('res_ini') or ultima['mapa'].get('resultado_ini') or ultima['dur'] * 0.6
            dur_v = max(0.5, it['dur'] - 0.05)  # el vídeo arranca con la tarjeta: la vista previa entra a 0,15 s
            desde = max(0.0, min(ru - 1.3, ultima['dur'] - dur_v - 0.1))
            src = self.video_escena(ultima['id'])
            img = self.foto(primera['id'], 0.0, f"{primera['id']}-primero")
            prev_html = (f'<div class="preview" style="left:0;top:0;width:1560px;height:878px"><div class="lienzo">'
                         f'{video_tag("v-" + it["id"], src, ini + 0.05, dur_v, desde)}<img class="primera" src="{img}" style="opacity:0"></div></div>')
        etq = f"{n:02d} / {total:02d} · {verbo} · {p.get('rol', '')}".upper().rstrip(' ·')
        if len(etq) * 21 * 0.7 > 840:  # JetBrains Mono a 21 px con espaciado de 0,1 em: si no cabe en la columna, sin el rol
            etq = f"{n:02d} / {total:02d} · {verbo}".upper()
        datos = {'id': it['id'], 'tipo': 'funcionalidad', 'ini': round(ini, 4), 'dur': it['dur'], 'pie': True,
                 'etiqueta': etq, 'titulo_lineas': lineas_html(lineas),
                 'para_que': html.escape(p['para_que']), 'persona': per, 'bases': [chip_base(b) for b in p['bases']],
                 'resultado': html.escape(p['resultado']), 'raya': raya, 'y0': y0, 'pv': pv}
        return datos, f'<div class="pieza func" id="p-{it["id"]}">{prev_html}</div>'

    def mapa(self, it: dict, b0: float) -> tuple[dict, str]:
        p = it['p']
        L = self.L
        destacar = p.get('destacar')
        ids = [b for b in (p.get('bloques') or [b['id'] for b in L['catalogo_mapa']]) if b in L['mapa_bloques']]
        n = len(ids)
        cols = 4 if n > 6 else 3
        filas = math.ceil(n / cols)
        gap = 24
        w = (1560 - gap * (cols - 1)) / cols
        h = 310 if filas > 1 else 360
        gap_v = 20
        y_tes = 270
        actual_orden = L['mapa_bloques'][destacar]['orden'] if destacar else None
        verbos_t = {}
        if not destacar:
            for b in ids:
                verbos_t[b] = momento_palabra(it['voz'], L['mapa_bloques'][b]['verbo'])
        teselas = []
        for k, b in enumerate(ids):
            mb = L['mapa_bloques'][b]
            fs = [(L['num_f'][fx], html.escape(NOMBRES_CORTOS.get(L['funcs'][fx]['nombre'], L['funcs'][fx]['nombre'])))
                  for fx in mb['funcionalidades'] if fx in L['num_f']]
            estado = ''
            if destacar:
                estado = 'actual' if b == destacar else ('hecho' if mb['orden'] < actual_orden else '')
            aparece = None
            if not destacar and it['entrada'] != 'continua':
                tv = verbos_t.get(b)
                aparece = (tv - 0.1) if tv is not None else (0.5 + 0.12 * k if mb['orden'] == 1 else it['dur'] - 2.6)
                aparece = max(0.4, min(aparece, it['dur'] - 1.6))
            teselas.append({'id': b, 'num': f"{mb['orden']:02d}", 'verbo': html.escape(mb['verbo']), 'titulo': html.escape(mb['titulo']),
                            'icono': mb['icono'], 'funcs': fs, 'ciclo': bool(mb.get('ciclo')), 'estado': estado, 'aparece': aparece,
                            'x': round(180 + (k % cols) * (w + gap), 1), 'y': y_tes + (k // cols) * (h + gap_v), 'w': round(w, 1), 'h': h})
        flechas = []
        for k in range(len(teselas) - 1):
            a0, a1 = teselas[k], teselas[k + 1]
            if a0['ciclo'] and a1['ciclo'] and a0['y'] == a1['y']:
                flechas.append({'x': round(a0['x'] + a0['w'], 1), 'y': a0['y'] + h / 2 - 12})
        if destacar:
            mb = L['mapa_bloques'][destacar]
            etiqueta = f"Bloque {mb['orden']} de {len(L['catalogo_mapa'])} · {mb['verbo']}" if not L['resumen'] else p.get('etiqueta', '')
            titulo = mb['titulo']
            sub = None
            tam = 54
        else:
            etiqueta = p.get('etiqueta', 'Mapa de funcionalidades')
            titulo = p.get('titulo', '')
            sub = p.get('subtitulo')
            tam = 44
        lineas = partir(titulo, fuente_pil('archivo', tam, 800, 100), 1560, 2)
        patron = None
        if not destacar and momento_palabra(it['voz'], 'quién') is not None:
            pasos = [('quién', 'Quién la usa'), ('para qué', 'Para qué sirve'), ('la prueba', 'La prueba real'), ('el resultado', 'El resultado')]
            patron = [{'texto': txt, 't': round((momento_palabra(it['voz'], w) or 0) - 0.1, 3)} for w, txt in pasos]
        datos = {'id': it['id'], 'tipo': 'mapa', 'patron': patron, 'ini': round(it['ini'] - b0, 4), 'dur': it['dur'], 'etiqueta': etiqueta.upper(),
                 'titulo_lineas': lineas_html(lineas), 'subtitulo': html.escape(sub) if sub else None, 'tam_titulo': tam,
                 'y_cab': 70 if sub else 96, 'teselas': teselas, 'flechas': flechas, 'salida': it['salida'],
                 'flechas_aparecen': (max(t['aparece'] or 0 for t in teselas) + 0.3) if not destacar and it['entrada'] != 'continua' else None}
        return datos, f'<div class="pieza mapa" id="p-{it["id"]}"></div>'

    def portada(self, it: dict, b0: float) -> tuple[dict, str]:
        p = it['p']
        titular = 'El conocimiento experto se queda en la empresa.'
        lineas = partir(titular, fuente_pil('archivo', 88, 800, 104), 840, 3)
        capt = []
        for k, (sid, t) in enumerate(self.momentos_portada()):
            img = self.foto(sid, t, f'portada-{k}', ancho=760)
            capt.append(img)
        pos = [(1080, 150), (1020, 300), (960, 450)]
        imgs = ''.join(f'<div class="captura" style="position:absolute;left:{x}px;top:{y}px;width:760px;height:428px;border-radius:16px;'
                       f'overflow:hidden;box-shadow:0 26px 50px rgba(0,0,0,.55);background:#fff"><img src="{c}" style="width:760px;height:428px;display:block"></div>'
                       for c, (x, y) in zip(capt, pos))
        datos = {'id': it['id'], 'tipo': 'portada', 'ini': round(it['ini'] - b0, 4), 'dur': it['dur'], 'pie': False,
                 'etiqueta': 'V DESAFÍO industrial · POLO positivo'.upper(), 'titulo_lineas': lineas_html(lineas),
                 'subtitulo': html.escape(p.get('subtitulo', '')), 'equipo': 'Rodrigo Pascual · Lydia Blanco · Gadea Lucas · Universidad de Burgos',
                 'y0': 300}
        return datos, f'<div class="pieza portada" id="p-{it["id"]}">{imgs}</div>'

    def buscar(self, ids: list[str]) -> str | None:
        """La primera de estas escenas que está en el vídeo (también con el sufijo -r del resumen)."""
        for sid in ids:
            for s in (sid, sid + '-r'):
                if s in self.por_id:
                    return s
        return None

    def momentos_portada(self) -> list[tuple[str, float]]:
        out = []
        for ids, marca in ((['09b-matriz-javier'], 'matriz'), (['03b-borrador-carmen'], 'borrador'), (['06-planta-lucia'], 'respuesta')):
            sid = self.buscar(ids)
            if sid:
                m = self.por_id[sid]['mapa']
                out.append((sid, m['marcas'].get(marca, 1.0) + 1.0))
        return out

    def problema(self, it: dict, b0: float) -> tuple[dict, str]:
        p = it['p']
        lineas = partir(p.get('titulo', 'El conocimiento se jubila'), fuente_pil('archivo', 72, 800, 100), 1560, 2)
        datos = {'id': it['id'], 'tipo': 'problema', 'ini': round(it['ini'] - b0, 4), 'dur': it['dur'], 'pie': False,
                 'etiqueta': p.get('etiqueta', 'El problema').upper(), 'titulo_lineas': lineas_html(lineas),
                 # Las cifras cuentan desde que entra la tarjeta (revisión: 5 s con las barras vacías era un tramo quieto).
                 'cifras': [{'valor': 5.3, 'texto': 'personas mayores de 55 años saldrán del mercado laboral', 'color': '#F07A62', 'ancho': 1100,
                             't': 0.7},
                            {'valor': 1.8, 'texto': 'jóvenes entrarán a trabajar', 'color': '#3CC49C', 'ancho': round(1100 * 1.8 / 5.3),
                             't': 1.3}],
                 'fuente': 'De 2026 a 2035 · Fundación Adecco a partir de la EPA'}
        return datos, f'<div class="pieza" id="p-{it["id"]}"></div>'

    def reparto(self, it: dict, b0: float) -> tuple[dict, str]:
        p = it['p']
        personas = []
        for q in p.get('personas', []):
            nombrada = momento_palabra(it['voz'], q['nombre'].split()[0])
            personas.append({'nombre': html.escape(q['nombre']), 'iniciales': q['iniciales'], 'color': color_avatar(q['nombre']),
                             'papel': html.escape(q['papel']), 'departamento': html.escape(q['departamento']),
                             'nombrada': (nombrada - 0.05) if nombrada is not None else None})
        lineas = partir(p.get('titulo', ''), fuente_pil('archivo', 60, 800, 100), 1560, 2)
        datos = {'id': it['id'], 'tipo': 'reparto', 'ini': round(it['ini'] - b0, 4), 'dur': it['dur'],
                 'etiqueta': p.get('etiqueta', '').upper(), 'titulo_lineas': lineas_html(lineas), 'personas': personas}
        return datos, f'<div class="pieza" id="p-{it["id"]}"></div>'

    def criterios(self, it: dict, b0: float) -> tuple[dict, str]:
        """Los cinco criterios de las bases: filas compactas a la izquierda y, a la derecha, el criterio que nombra la voz
        en grande con su prueba: el tablero de los 30 puntos para la cobertura y, para los demás, 3 s de la toma real que
        crece desde su miniatura y vuelve a ella (revisión del 11/10)."""
        p = it['p']
        L = self.L
        ini = it['ini'] - b0
        pruebas = {1: (['12a-organizacion-admin'], 'reglas', 0.3), 2: (['12c2-modelos-admin'], 'nube', 1.0),
                   3: (['05b-socratico-marta'], 'respuesta', 0.2), 4: (['06-planta-lucia'], 'respuesta', 0.3)}
        tiempos = []
        for i, c in enumerate(p['criterios']):
            t = next((v['ini'] for v in it['voz'] if v.get('criterio') == i), 1.0 + 3 * i)
            if i == 0:
                t = momento_palabra(it['voz'], 'Cobertura funcional') or t
            tiempos.append(round(max(0.6, t - 0.1), 3))
        filas, html_v = [], ''
        for i, c in enumerate(p['criterios']):
            t = tiempos[i]
            sig = tiempos[i + 1] if i + 1 < len(tiempos) else it['dur'] - 0.4
            texto = c['texto']
            if i == 0 and L['resumen']:
                texto = texto.replace('se demuestran', 'se demuestran en el recorrido completo')
            fila = {'peso': c['peso'], 'nombre': html.escape(c['nombre']), 'texto': html.escape(texto), 't': t, 'fin': round(sig, 3)}
            ids, marca, adelanto = pruebas.get(i, (None, None, 0))
            sid = None
            if ids:
                sid = self.buscar(ids) or (ids[0] if self.existe(ids[0]) else None)
            if sid:
                m = self.mapa_de(sid)
                desde = min(m['marcas'].get(marca, m['duracion'] / 2) + adelanto, m['duracion'] - 3.2)
                dur_c = round(max(1.5, min(3.0, sig - t - 0.9)), 3)
                src = self.video_escena(sid)
                fila['clip'] = {'ini': round(t + 0.45, 3), 'dur': dur_c}
                fila['img'] = self.foto(sid, desde + 0.1, f'criterio-{i}-a', ancho=800)
                fila['img_fin'] = self.foto(sid, desde + dur_c - 0.1, f'criterio-{i}-b', ancho=800)
                html_v += (f'<div class="cm" id="cm-{i}"><img class="a" src="{fila["img"]}">'
                           f'{video_tag(f"v-crit-{i}", src, ini + t + 0.45, dur_c, desde)}<img class="b" src="{fila["img_fin"]}"></div>')
            filas.append(fila)
        cob = [x for x in (L['catalogo'].get('cobertura_bases') or []) if x['bloque'] != 'Requisitos generales']
        celdas = ['ok' if x['estado'] == '✓' else 'medio' for x in cob]
        celdas.sort(key=lambda c: c != 'ok')
        ok = celdas.count('ok')
        t27 = momento_palabra(it['voz'], '27 de los 30') or (filas[0]['t'] + 2.0)
        lineas = partir('Cinco criterios, una prueba en pantalla para cada uno', fuente_pil('archivo', 54, 800, 104), 1700, 2)
        donde = 'en el recorrido completo' if L['resumen'] else 'en el vídeo'
        datos = {'id': it['id'], 'tipo': 'criterios', 'ini': round(ini, 4), 'dur': it['dur'],
                 'etiqueta': p.get('etiqueta', 'Cómo cubre las bases').upper(), 'titulo_lineas': lineas_html(lineas), 'criterios': filas,
                 'cobertura': {'titulo': f'{ok} de {len(celdas)} puntos del alcance', 'sub': f'demostrados {donde}; {len(celdas) - ok} simplificados',
                               'celdas': celdas, 't': round(t27 - 0.2, 3)}}
        return datos, f'<div class="pieza criterios" id="p-{it["id"]}"><div class="crit-media">{html_v}</div></div>'

    def implantacion(self, it: dict, b0: float) -> tuple[dict, str]:
        p = it['p']
        im = p.get('implantacion', {})
        lineas = partir(p.get('titulo', ''), fuente_pil('archivo', 60, 800, 104), 1560, 2)
        t2 = it['voz'][1]['ini'] if len(it['voz']) > 1 else it['dur'] - 3
        # Composición centrada (revisión del 11/10): los dos instaladores arriba, la cifra grande en el centro y las
        # licencias debajo, sin nombres de fichero de desarrollo.
        tarjetas = [
            {'icono': 'laptop', 'nombre': html.escape(im.get('puestos', {}).get('nombre', 'CidIA-Setup.exe')),
             'texto': html.escape(im.get('puestos', {}).get('texto', '')), 't': 0.7},
            {'icono': 'server', 'nombre': html.escape(im.get('servidor', {}).get('nombre', 'instalar-servidor.sh')),
             'texto': html.escape(im.get('servidor', {}).get('texto', '')), 't': 1.1},
        ]
        coste = {'gran': '6.217,78 €', 'texto': '1 servidor y 5 puestos, con IVA, en hardware · sin cuotas ni pago por consulta',
                 't': max(1.6, (momento_palabra(it['voz'], 'un servidor y cinco') or 3.0) - 0.2)}
        lic = (p.get('licencias') or ['Software libre con licencias que permiten el uso comercial: detalle de licencias en la documentación del proyecto.'])[0]
        datos = {'id': it['id'], 'tipo': 'implantacion', 'ini': round(it['ini'] - b0, 4), 'dur': it['dur'],
                 'etiqueta': p.get('etiqueta', '').upper(), 'titulo_lineas': lineas_html(lineas), 'tarjetas': tarjetas, 'coste': coste,
                 'licencias': html.escape(lic), 't_licencias': round(t2 - 0.1, 3)}
        return datos, f'<div class="pieza" id="p-{it["id"]}"></div>'

    def final(self, it: dict, b0: float) -> tuple[dict, str]:
        recs = [('Capturar', ['03b-borrador-carmen'], 'borrador'), ('Estructurar', ['04b-probar-busqueda-ana'], 'resultados'),
                ('Formar', ['07b-microleccion-tutor-lucia'], 'control'), ('Acompañar', ['06-planta-lucia', '06-planta-lucia-r'], 'respuesta'),
                ('Evaluar', ['08c-observacion-javier'], 'nivel'), ('Certificar', ['09b-matriz-javier'], 'matriz')]
        recap, html_r = [], ''
        for k, (verbo, ids, marca) in enumerate(recs):
            sid = self.buscar(ids)
            img = ''
            if sid:
                m = self.por_id[sid]['mapa']
                img = self.foto(sid, m['marcas'].get(marca, m['duracion'] / 2) + 0.8, f'recap-{k}', ancho=520)
            recap.append({'verbo': verbo})
            x, y = 156 + (k % 3) * 544, 200 + (k // 3) * 316
            html_r += f'<div class="recap" style="left:{x}px;top:{y}px"><img src="{img}"><span class="v">{verbo}</span></div>'
        paso = 0.42
        t_lock = 0.25 + 6 * paso + 0.75
        datos = {'id': it['id'], 'tipo': 'final', 'ini': round(it['ini'] - b0, 4), 'dur': it['dur'], 'pie': False, 'recap': recap, 'paso': paso,
                 't_lockup': round(t_lock, 3), 'lema': 'El conocimiento se queda.', 'claves': 'EN LOCAL · SOFTWARE LIBRE · SIN PAGO POR CONSULTA',
                 'equipo': 'Rodrigo Pascual · Lydia Blanco · Gadea Lucas · Universidad de Burgos',
                 'convocatoria': 'V DESAFÍO industrial · POLO positivo',
                 # Notas de veracidad: encima de la franja de subtítulos, a 20 px y en niebla (revisión del 11/10).
                 'creditos': ['Datos sintéticos de una empresa ficticia, Metalúrgica Arlanza, S. L. Todo lo que se ve es la app real,',
                              'en un servidor de pruebas con modelos pequeños; en una empresa, CidIA va en su propio servidor.',
                              'Voces sintéticas generadas en local con Supertonic 3 y Kokoro-82M · Música y efectos propios',
                              'Esperas del servidor aceleradas y rotuladas con su tiempo real']}
        return datos, f'<div class="pieza final" id="p-{it["id"]}">{html_r}</div>'

    def apertura(self, it: dict, b0: float) -> tuple[dict, str]:
        frases = ['Pregunta en el <em>puesto</em>.', 'Captura lo que sabe la <em>experta</em>.', 'Certifica con <em>evidencias</em>.']
        elegidos = [(['06-planta-lucia', '06-planta-lucia-r'], 'respuesta'), (['03b-borrador-carmen'], 'borrador'), (['09b-matriz-javier'], 'matriz')]
        clips, html_c = [], ''
        for k, ((ids, marca), frase) in enumerate(zip(elegidos, frases)):
            sid = self.buscar(ids)
            if not sid:
                continue
            m = self.por_id[sid]['mapa']
            t0 = m['marcas'].get(marca, 1.0) + 0.25
            # Encuadre: el primer resaltado que empieza cerca de ese momento.
            acc = next((a for a in m['acciones'] if a['tipo'].startswith('resaltar') and a['ini'] >= t0 - 0.6 and a.get('elemento')), None)
            cx, cy, z = encuadre((acc['elemento']['x'], acc['elemento']['y'], acc['elemento']['w'], acc['elemento']['h']), 1.4) if acc else REPOSO
            ini_c = 2.0 * k
            src = self.video_escena(sid)
            clips.append({'ini': ini_c, 'dur': 2.0, 'cx': cx, 'cy': cy, 'z0': max(1.0, z * 0.95), 'z1': max(1.0, z), 'frase': frase})
            desde = min((acc['ini'] + 0.55) if acc else t0, m['duracion'] - 2.1)
            html_c += (f'<div class="marco"><div class="camara">{video_tag(f"v-ap-{k}", src, it["ini"] - b0 + ini_c, 2.0, desde)}'
                       f'</div></div>')
        datos = {'id': it['id'], 'tipo': 'apertura', 'ini': round(it['ini'] - b0, 4), 'dur': it['dur'], 'pie': False, 'clips': clips}
        return datos, f'<div class="pieza apertura" id="p-{it["id"]}">{html_c}</div>'

    # -- bloque
    def bloque(self, b: dict, subs: list[dict]) -> Path:
        b0, b1 = b['ini'], b['fin']
        datos_p, html_p = [], []
        for it in self.items:
            if it['bloque'] != b['id']:
                continue
            f = getattr(self, it['tipo'])
            d, h = f(it, b0)
            datos_p.append(d)
            html_p.append(h)
        subs_b = []
        for c in subs:
            if c['fin'] <= b0 or c['ini'] >= b1:
                continue
            x = {'tipo': c['tipo'], 'ini': round(c['ini'] - b0, 3), 'fin': round(c['fin'] - b0, 3)}
            if c['tipo'] == 'micro':
                x['quien'] = html.escape(c['quien'])
                x['palabras'] = [{'w': w['w'], 't': round(w['t'] - b0, 3), 'br': w.get('br', False)} for w in c['palabras']]
            else:
                x['html'] = resaltar(montaje.partir_lineas(c['texto'], 56))
            subs_b.append(x)
        ultimo = self.items[-1]
        datos = {'duracion': round(b1 - b0, 4), 'desde': b0, 'fondo': 'media/fondo.png', 'piezas': datos_p, 'subtitulos': subs_b,
                 'rail': [{**r, 'x': r['x'], 'w': r['w']} for r in self.L['rail']],
                 'cortinillas': [round(c - b0, 4) for c in self.L['cortinillas'] if b0 - 0.31 <= c <= b1 + 0.31],
                 'desde_negro': b0 == 0, 'a_negro': round(ultimo['ini'] + ultimo['dur'] - 1.0 - b0, 4) if ultimo['bloque'] == b['id'] else None,
                 'iconos': self.L['iconos']}
        cid = f"bloque-{b['id']}"
        texto_datos = json.dumps(datos, ensure_ascii=False).replace('</', '<\\/')
        doc = ('<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'
               f'<title>CidIA v2 · {cid}</title>\n<link rel="stylesheet" href="cidia-v2.css">\n</head>\n<body>\n'
               f'<div class="raiz" id="raiz" data-composition-id="{cid}" data-start="0" data-width="1920" data-height="1080" '
               f'data-duration="{b1 - b0:.4f}">\n' + '\n'.join(html_p) +
               f'\n<script type="application/json" id="datos-cidia">{texto_datos}</script>\n'
               '<script src="lib/gsap.min.js"></script>\n<script src="cidia-v2.js"></script>\n'
               f'<script>window.__timelines = window.__timelines || {{}};\nwindow.__timelines["{cid}"] = window.__cidiaTimeline;</script>\n'
               '</div>\n</body>\n</html>\n')
        # Cada bloque es un proyecto de HyperFrames con su index.html (una sola composición raíz por proyecto, como
        # pide su linter) y sus medios enlazados: fuentes, GSAP, CSS, director, fondo, vídeos limpios y fotos.
        carpeta = self.hf / b['id']
        if carpeta.exists():
            shutil.rmtree(carpeta)
        (carpeta / 'media').mkdir(parents=True)
        for rel, origen in {**self.necesarios, 'media/fondo.png': self.comun / 'fondo.png'}.items():
            enlazar(origen, carpeta / rel)
        for f in (self.comun / 'base').rglob('*'):
            if f.is_file():
                enlazar(f, carpeta / f.relative_to(self.comun / 'base'))
        self.necesarios = {}
        destino = carpeta / 'index.html'
        destino.write_text(doc, encoding='utf-8')
        return destino


def componer(a: argparse.Namespace) -> None:
    trab = Path(a.trabajo).resolve()
    linea = leer(trab / 'linea.json')
    hf = trab / 'hf'
    base = hf / 'comun' / 'base'
    # Las fotos se sacan de los vídeos ya procesados (tapas, congelados...): se rehacen siempre, son pocas.
    shutil.rmtree(hf / 'comun' / 'fotos', ignore_errors=True)
    (base / 'lib').mkdir(parents=True, exist_ok=True)
    (base / 'fuentes').mkdir(parents=True, exist_ok=True)
    (hf / 'comun' / 'fotos').mkdir(parents=True, exist_ok=True)
    shutil.copy2(GSAP, base / 'lib' / 'gsap.min.js')
    for n in ('cidia-v2.css', 'cidia-v2.js'):
        shutil.copy2(ACTIVOS / n, base / n)
    shutil.copy2(F_ARCHIVO, base / 'fuentes' / 'Archivo.ttf')
    shutil.copy2(F_MONO, base / 'fuentes' / 'JetBrainsMono.ttf')
    for f in F_FIRA.glob('FiraSans-*.ttf'):
        shutil.copy2(f, base / 'fuentes' / f.name)
    for f in list(F_FIRA.glob('OFL*.txt')) + list((F_FIRA / 'v2').glob('OFL-*.txt')):
        shutil.copy2(f, base / 'fuentes' / (f.name if f.name != 'OFL.txt' else 'OFL-FiraSans.txt'))
    fondo_png(hf / 'comun' / 'fondo.png')
    iconos = leer(ACTIVOS / 'iconos.json')
    linea['iconos'] = iconos['iconos']
    linea['catalogo_mapa'] = list(linea['mapa_bloques'].values())
    subs = linea['subtitulos']
    comp = Compositor(linea, trab)
    hechos = []
    solo = set(a.bloques.split(',')) if getattr(a, 'bloques', None) else None
    for b in linea['bloques']:
        if solo and b['id'] not in solo:
            continue
        hechos.append(comp.bloque(b, subs))
    # Con --bloques solo se calculan las cámaras de esos bloques: se mezclan con las que ya había.
    camaras = leer(trab / 'camaras.json') if (solo and (trab / 'camaras.json').exists()) else {}
    camaras.update({it['id']: it['_camara'] for it in comp.items if it['tipo'] == 'escena' and it.get('_camara') is not None})
    escribir(trab / 'camaras.json', camaras)
    print(f'Proyecto HyperFrames: {hf} ({len(hechos)} bloques)')


# ---------------------------------------------------------------------------------------------- línea: pasos
def secciones_musica(L: dict) -> list[list]:
    items = L['items']
    secs: list[list] = []
    ap = next((it for it in items if it['tipo'] == 'apertura'), None)
    po = next((it for it in items if it['tipo'] == 'portada'), None)
    if ap:
        secs.append([ap['ini'], ap['ini'] + ap['dur'], 'apertura'])
    if po:
        secs.append([po['ini'], po['ini'] + po['dur'], 'portada'])
    k = 0
    for b in L['bloques']:
        b0, b1 = b['ini'], b['fin']
        if secs:
            b0 = max(b0, secs[-1][1])
        if b1 - b0 < 0.5:
            continue
        if b['id'] == 'cierre':
            cr = next((it for it in items if it['tipo'] == 'criterios'), None)
            im = next((it for it in items if it['tipo'] == 'implantacion'), None)
            c0 = im['ini'] if im else b0
            if cr and cr['ini'] < c0:
                secs.append([max(b0, cr['ini']), c0, 'bases'])
            secs.append([c0, b1, 'cierre'])
            continue
        secs.append([b0, b1, 'bloque_a' if k % 2 == 0 else 'bloque_b'])
        k += 1
    return [[round(a, 3), round(b, 3), t] for a, b, t in secs]


LOGRO = re.compile(r'(aprob|valid|nivel|registrad|publica)', re.I)


def efectos(L: dict) -> list[dict]:
    ev = []
    for it in L['items']:
        g = it['ini']
        if it['tipo'] == 'portada':
            ev.append({'t': round(g - 1.0, 3), 'tipo': 'golpe'})
        if it['entrada'] == 'cortinilla':
            ev.append({'t': round(g - 0.3, 3), 'tipo': 'soplo'})
        elif it['entrada'] == 'empuje':
            ev.append({'t': round(g, 3), 'tipo': 'soplo', 'db': -5})
        if it['tipo'] != 'escena':
            continue
        m = it['mapa']
        ult = -9.0
        micro = [(a['ini'], a['fin']) for a in m['acciones'] if a['tipo'] == 'mantenerMicro' and a.get('visible')]
        for r in m['raton']:
            if r['ev'] != 'pulsar' or r['t'] >= it['dur'] - 0.3 or r['t'] - ult < 0.9:
                continue
            if any(a0 - 0.1 <= r['t'] <= a1 + 0.1 for a0, a1 in micro):
                continue
            ev.append({'t': round(g + r['t'], 3), 'tipo': 'clic'})
            ult = r['t']
        for a0, a1 in micro:
            if a1 < it['dur']:
                ev.append({'t': round(g + a0 + 0.05, 3), 'tipo': 'pitido'})
                ev.append({'t': round(g + a1, 3), 'tipo': 'pitido'})
        r = it['p'].get('resultado')
        if isinstance(r, dict) and it.get('res_ini') is not None and LOGRO.search(r['texto']):
            ev.append({'t': round(g + it['res_ini'] + 0.4, 3), 'tipo': 'confirmacion'})
    return sorted(ev, key=lambda e: e['t'])


def capitulos(L: dict) -> list[list]:
    caps: list[list] = []
    for it in L['items']:
        nombre = it.get('capitulo') or (L['items'][1].get('capitulo') if it['tipo'] == 'apertura' and len(L['items']) > 1 else None)
        if nombre and (not caps or caps[-1][1] != nombre):
            caps.append([round(it['ini'], 3), nombre])
    if caps and caps[0][0] > 0:
        caps[0][0] = 0.0
    return caps


def paso_linea(a: argparse.Namespace) -> dict:
    trab = Path(a.trabajo).resolve()
    L = construir_linea(a)
    L['subtitulos'] = subtitulos(L)
    L['musica'] = secciones_musica(L)
    L['efectos'] = efectos(L)
    L['capitulos'] = capitulos(L)
    escribir(trab / 'linea.json', L)
    srt(L['subtitulos'], trab / 'subtitulos.srt')
    n_esc = sum(1 for it in L['items'] if it['tipo'] == 'escena')
    print(f"Línea: {L['duracion'] / 60:.1f} min ({L['duracion']:.1f} s), {len(L['items'])} piezas ({n_esc} escenas), "
          f"{len(L['bloques'])} bloques, {len(L['subtitulos'])} subtítulos, {len(L['efectos'])} efectos, {len(L['capitulos'])} capítulos")
    for b in L['bloques']:
        print(f"  bloque {b['id']:<7} {b['ini']:7.1f} a {b['fin']:7.1f} s  ({b['fin'] - b['ini']:5.1f} s)")
    return L


def paso_escenas(a: argparse.Namespace) -> None:
    trab = Path(a.trabajo).resolve()
    ns = SimpleNamespace(proyecto=a.proyecto, grabaciones=a.grabaciones, voces=a.voces, limpio=str(trab / 'escenas'),
                         solo=getattr(a, 'solo', None), rampa=0.3, sin_recortes_auto=False, forzar=getattr(a, 'forzar', False))
    montaje.main_limpio(ns)


# ---------------------------------------------------------------------------------------------- render
def entorno_hf() -> dict:
    env = os.environ.copy()
    ff = Path(ffmpeg())
    env.update({'HYPERFRAMES_NO_TELEMETRY': '1', 'DO_NOT_TRACK': '1', 'HYPERFRAMES_NO_UPDATE_CHECK': '1',
                'HYPERFRAMES_NO_AUTO_INSTALL': '1', 'HYPERFRAMES_SKIP_SKILLS': '1',
                'HYPERFRAMES_FFMPEG_PATH': str(ff), 'HYPERFRAMES_FFPROBE_PATH': str(ff.with_name('ffprobe' + ff.suffix))})
    env['PATH'] = str(ff.parent) + os.pathsep + env.get('PATH', '')
    return env


def hf_cli(*args: str, registro: Path | None = None, cwd: Path | None = None) -> int:
    cmd = ['node', str(HF / 'node_modules' / 'hyperframes' / 'bin' / 'hyperframes.mjs'), *args]
    with open(registro, 'a', encoding='utf-8') if registro else open(os.devnull, 'w') as log:
        log.write('\n$ ' + ' '.join(cmd) + '\n')
        log.flush()
        r = subprocess.run(cmd, env=entorno_hf(), cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
    return r.returncode


def limpiar_cache_hf() -> float:
    """Borra las cachés de fotogramas que HyperFrames deja en %TEMP% (solo las suyas)."""
    libre = 0.0
    tmp = Path(os.environ.get('TEMP') or os.environ.get('TMP') or '/tmp')
    for d in tmp.glob('hyperframes-*'):
        if d.is_dir():
            libre += sum(f.stat().st_size for f in d.rglob('*') if f.is_file()) / 1e9
            shutil.rmtree(d, ignore_errors=True)
    return libre


def duracion_video(p: Path) -> float:
    r = correr([str(Path(ffmpeg()).with_name('ffprobe' + Path(ffmpeg()).suffix)), '-v', 'error', '-select_streams', 'v:0',
                '-count_packets', '-show_entries', 'stream=nb_read_packets,r_frame_rate', '-of', 'json', str(p)])
    s = json.loads(r.stdout)['streams'][0]
    return int(s['nb_read_packets']) / FPS


def paso_render(a: argparse.Namespace) -> None:
    trab = Path(a.trabajo).resolve()
    L = leer(trab / 'linea.json')
    hf = trab / 'hf'
    salida = trab / 'bloques'
    salida.mkdir(exist_ok=True)
    solo = set(a.bloques.split(',')) if a.bloques else None
    tiempos = leer(trab / 'tiempos.json') if (trab / 'tiempos.json').exists() else {}
    registro = trab / 'render.log'
    for b in L['bloques']:
        if solo and b['id'] not in solo:
            continue
        html_b = hf / b['id'] / 'index.html'
        out = salida / f"{b['id']}.mp4"
        if out.exists() and not a.forzar and out.stat().st_mtime > html_b.stat().st_mtime:
            print(f"  bloque {b['id']}: ya renderizado")
            continue
        libre = shutil.disk_usage(trab).free / 1e9
        if libre < 4:
            raise SystemExit(f'Solo quedan {libre:.1f} GB libres: libera espacio antes de seguir')
        t0 = time.time()
        rc = hf_cli('render', str(html_b.parent), '-o', str(out), '--gpu', '--quality', 'high', '--fps', '30',
                    '--video-frame-format', a.formato, '--workers', str(a.workers), '--browser-timeout', '300', registro=registro)
        dt = time.time() - t0
        borrado = limpiar_cache_hf()
        if rc != 0 or not out.exists():
            raise SystemExit(f"El render del bloque {b['id']} falló (código {rc}); mira {registro}")
        d_real, d_pedida = duracion_video(out), b['fin'] - b['ini']
        tiempos[b['id']] = {'segundos_video': round(d_pedida, 2), 'render_s': round(dt, 1), 'fotogramas': round(d_real * FPS),
                            'workers': a.workers, 'cache_borrada_gb': round(borrado, 2)}
        escribir(trab / 'tiempos.json', tiempos)
        aviso = '' if abs(d_real - d_pedida) < 1.5 / FPS else f'  ¡OJO: {d_real:.3f} s y se pedían {d_pedida:.3f} s!'
        print(f"  bloque {b['id']}: {d_pedida:6.1f} s de vídeo en {dt / 60:5.1f} min  ({out.stat().st_size / 1e6:.0f} MB){aviso}")


# ---------------------------------------------------------------------------------------------- audio
def nivel_k(x: np.ndarray) -> float:
    """Valor cuadrático medio ponderado en K (BS.1770) sobre los bloques de 400 ms con señal, en dB."""
    # Aproximación rápida en frecuencia: realce de agudos (+4 dB por encima de 1,5 kHz) y corte de graves (< 60 Hz).
    n = 1 << int(math.ceil(math.log2(max(len(x), 2))))
    X = np.fft.rfft(x, n)
    f = np.fft.rfftfreq(n, 1 / TASA)
    g = (1 / np.sqrt(1 + (60 / np.maximum(f, 1)) ** 4)) * (1 + (10 ** (4 / 20) - 1) / (1 + (1500 / np.maximum(f, 1)) ** 2))
    y = np.fft.irfft(X * g, n)[:len(x)]
    blq = int(0.4 * TASA)
    m = len(y) // blq
    if m == 0:
        return -99.0
    e = np.mean(y[:m * blq].reshape(m, blq) ** 2, axis=1)
    e = e[e > 1e-8]
    if not len(e):
        return -99.0
    rel = 10 * np.log10(np.mean(e)) - 10
    e = e[10 * np.log10(e) > rel]
    return float(10 * np.log10(np.mean(e)))


def envolvente(x: np.ndarray, ref_db: float, ataque: float = 0.06, suelta: float = 1.0, retencion: float = 0.3) -> np.ndarray:
    """Presencia de voz (0 a 1) cada 10 ms con ataque, retención y suelta, y de vuelta a 48 kHz. La retención (300 ms)
    y la suelta lenta (1 s) evitan que el fondo suba y baje en cada hueco entre frases (el «bombeo» de la revisión)."""
    blq = TASA // 100
    nb = int(math.ceil(len(x) / blq))
    v = np.zeros(nb * blq, np.float32)
    v[:len(x)] = x
    e = np.sqrt(np.mean(v.reshape(nb, blq) ** 2, axis=1)) + 1e-9
    db = 20 * np.log10(e)
    p = np.clip((db - (ref_db - 32)) / 8, 0, 1)
    k_ret = int(round(retencion * 100))
    if k_ret > 0:
        from numpy.lib.stride_tricks import sliding_window_view
        p = sliding_window_view(np.concatenate([np.zeros(k_ret), p]), k_ret + 1).max(axis=1)
    out = np.zeros(nb, np.float32)
    ka, ks = math.exp(-0.01 / ataque), math.exp(-0.01 / suelta)
    s = 0.0
    for i in range(nb):
        kk = ka if p[i] > s else ks
        s = kk * s + (1 - kk) * p[i]
        out[i] = s
    return np.repeat(out, blq)[:len(x)]


def paso_audio(a: argparse.Namespace) -> None:
    trab = Path(a.trabajo).resolve()
    L = leer(trab / 'linea.json')
    total = L['duracion']
    n = int(round(total * TASA))
    voz = np.zeros(n, np.float32)
    mic = np.zeros(n, np.float32)
    for it in L['items']:
        for v in it['voz']:
            x = montaje.leer_wav(Path(v['wav'])) * float(v.get('ganancia', 1.0))
            i = int(round((it['ini'] + v['ini']) * TASA))
            fin_p = int(round((it['ini'] + it['dur']) * TASA))
            x = x[:max(0, min(len(x), fin_p - i, n - i))]
            (mic if v.get('microfono') else voz)[i:i + len(x)] += x
    activa = np.abs(voz) > 0.01
    ref = nivel_k(voz[activa]) if activa.any() else -20.0
    rms_voz_db = 20 * np.log10(np.sqrt(np.mean(voz[activa] ** 2)) + 1e-9)
    print(f'  voz: {ref:.1f} dB K ({rms_voz_db:.1f} dB RMS) en los tramos con voz')
    # Música: sin voz, unos 12 dB por debajo de la voz; bajo la voz se agacha 4 dB más (16 dB) con retención de 300 ms
    # y suelta de 1 s, y 4 dB más bajo el micrófono (revisión del 11/10: antes 10 + 6 dB con suelta de 0,45 s, que bombeaba).
    musica_st = musica.componer([tuple(s) for s in L['musica']], total).astype(np.float32)
    mono = musica_st.mean(axis=0)
    hay = np.abs(mono) > 1e-4
    nivel_m = nivel_k(mono[hay]) if hay.any() else -40.0
    musica_st *= 10 ** ((ref - 12 - nivel_m) / 20)
    p_voz = envolvente(voz, rms_voz_db)
    p_mic = envolvente(mic, rms_voz_db)
    agache = 10 ** ((-4 * p_voz - 4 * p_mic) / 20)
    musica_st *= agache[None, :]
    # Efectos.
    sfx = np.zeros((2, n), np.float32)
    sonidos = {'clic': (musica.clic(), -17), 'soplo': (musica.soplo(), -15), 'confirmacion': (musica.confirmacion(), -13),
               'pitido': (musica.pitido(), -17), 'golpe': (musica.golpe(), -3)}
    for e in L['efectos']:
        x, db = sonidos[e['tipo']]
        db += float(e.get('db', 0))
        act = np.abs(x) > 0.05 * np.max(np.abs(x))
        g = 10 ** ((rms_voz_db + db) / 20) / (np.sqrt(np.mean(x[act] ** 2)) + 1e-9)
        i = int(round(e['t'] * TASA))
        if i < 0:
            x = x[-i:]
            i = 0
        m = min(len(x), n - i)
        if m <= 0:
            continue
        if e['tipo'] == 'soplo':
            pan = np.linspace(-0.6, 0.6, m)
            sfx[0, i:i + m] += g * x[:m] * np.cos((pan + 1) * np.pi / 4)
            sfx[1, i:i + m] += g * x[:m] * np.sin((pan + 1) * np.pi / 4)
        else:
            sfx[:, i:i + m] += g * x[:m] * 0.7071
    mezcla = musica_st + sfx + (voz + mic)[None, :] * 0.7071 * 1.414
    pico = float(np.max(np.abs(mezcla)))
    mezcla *= min(1.0, 0.89 / max(pico, 1e-9))
    destino = trab / 'mezcla.wav'
    with wave.open(str(destino), 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(TASA)
        w.writeframes((np.clip(mezcla.T, -1, 1) * 32767).astype('<i2').tobytes())
    print(f"  mezcla: {destino} ({total:.1f} s, {len(L['efectos'])} efectos, música {len(L['musica'])} secciones)")


# ---------------------------------------------------------------------------------------------- final
def paso_final(a: argparse.Namespace) -> None:
    trab = Path(a.trabajo).resolve()
    L = leer(trab / 'linea.json')
    salida = Path(a.salida).resolve()
    salida.parent.mkdir(parents=True, exist_ok=True)
    bloques = [trab / 'bloques' / f"{b['id']}.mp4" for b in L['bloques']]
    falta = [b.name for b in bloques if not b.exists()]
    if falta:
        raise SystemExit(f'Faltan bloques por renderizar: {", ".join(falta)}')
    (trab / 'lista.txt').write_text(''.join(f"file '{b.as_posix()}'\n" for b in bloques), encoding='utf-8')
    total = L['duracion']
    # Capítulos.
    caps = L['capitulos']
    meta = [';FFMETADATA1', f"title={L.get('titulo') or 'CidIA'}", 'artist=CidIA', 'language=spa']
    for k, (t0, nombre) in enumerate(caps):
        t1 = caps[k + 1][0] if k + 1 < len(caps) else total
        meta += ['[CHAPTER]', 'TIMEBASE=1/1000', f'START={int(t0 * 1000)}', f'END={int(t1 * 1000)}', f'title={nombre}']
    (trab / 'capitulos.ffmeta').write_text('\n'.join(meta) + '\n', encoding='utf-8')
    txt_caps = ''.join(f'{int(t0 // 60)}:{int(t0 % 60):02d} {nombre}\n' for t0, nombre in caps)
    salida.with_suffix('.capitulos.txt').write_text(txt_caps, encoding='utf-8')
    (salida.parent / 'capitulos.txt').write_text(txt_caps, encoding='utf-8') if a.capitulos_comun else None
    shutil.copy2(trab / 'subtitulos.srt', salida.with_suffix('.srt'))
    # Volumen: loudnorm en dos pasadas (-16 LUFS, pico real -1,5 dBTP).
    med = correr([ffmpeg(), '-hide_banner', '-nostats', '-i', str(trab / 'mezcla.wav'), '-af',
                  'loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'])
    m = json.loads(med.stderr[med.stderr.rindex('{'):med.stderr.rindex('}') + 1])
    norm = (f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
            f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000")
    t0 = time.time()
    tmp = salida.with_name(salida.stem + '.tmp.mp4')
    # Cada bloque se recorta a sus fotogramas exactos antes de unirlos: el render de HyperFrames deja a veces uno de más y,
    # sumados, la imagen se iba retrasando respecto al sonido hasta 133 ms (revisión del 11/10).
    entradas, fc = [], []
    for k, (b, f) in enumerate(zip(L['bloques'], bloques)):
        entradas += ['-i', str(f)]
        fc.append(f"[{k}:v]trim=end_frame={int(round((b['fin'] - b['ini']) * FPS))},setpts=PTS-STARTPTS[b{k}]")
    nb = len(bloques)
    fc.append(''.join(f'[b{k}]' for k in range(nb)) + f'concat=n={nb}:v=1:a=0,fps={FPS},format=yuv420p[v]')
    # NVENC en lugar de OpenH264: con OpenH264 la tasa pedida no se respetaba (salía a unos 4 Mb/s) y los degradados de
    # las tarjetas hacían bandas. VBR con calidad constante 19 y 20 Mb/s de máximo (la
    # media sale de la calidad: unos 6 Mb/s, porque casi todo es interfaz quieta).
    correr([ffmpeg(), '-y', '-hide_banner', '-loglevel', 'error', *entradas,
            '-i', str(trab / 'mezcla.wav'), '-i', str(trab / 'capitulos.ffmeta'), '-i', str(trab / 'subtitulos.srt'),
            '-filter_complex', ';'.join(fc),
            '-map', '[v]', '-map', f'{nb}:a', '-map', f'{nb + 2}:s', '-map_metadata', str(nb + 1), '-map_chapters', str(nb + 1),
            '-c:v', 'h264_nvenc', '-preset', 'p7', '-tune', 'hq', '-profile:v', 'high', '-rc', 'vbr', '-cq', '19',
            '-b:v', a.bitrate, '-maxrate', '20M', '-bufsize', '24M', '-spatial-aq', '1', '-temporal-aq', '1', '-bf', '3',
            '-g', '60', '-r', '30', '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
            '-af', norm + ',aformat=channel_layouts=stereo', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
            '-c:s', 'mov_text', '-metadata:s:s:0', 'language=spa', '-metadata:s:a:0', 'language=spa',
            '-t', f'{total:.3f}', '-movflags', '+faststart', str(tmp)])
    tmp.replace(salida)
    dt = time.time() - t0
    tiempos = leer(trab / 'tiempos.json') if (trab / 'tiempos.json').exists() else {}
    tiempos['final'] = {'codificacion_s': round(dt, 1)}
    escribir(trab / 'tiempos.json', tiempos)
    informe = {'salida': str(salida), 'duracion_s': round(total, 2), 'capitulos': caps, 'subtitulos': len(L['subtitulos']),
               'loudnorm_entrada': {k: m[k] for k in ('input_i', 'input_tp', 'input_lra')}, 'tiempos': tiempos,
               'piezas': [{'id': it['id'], 'tipo': it['tipo'], 'inicio_s': round(it['ini'], 2), 'duracion_s': round(it['dur'], 2),
                           'entrada': it['entrada'], 'salida': it['salida'], 'bloque': it['bloque'],
                           **({'congelado_s': it['mapa']['congelado_s'], 'recortado_s': it['mapa']['recortado_s'],
                               'esperas': [{k: e[k] for k in ('factor', 'real', 'etiqueta')} for e in it['mapa']['esperas']],
                               'recortes_auto': it['mapa']['recortes']} if it['tipo'] == 'escena' else {})}
                          for it in L['items']]}
    escribir(salida.with_suffix('.informe.json'), informe)
    print(f'Listo: {salida} ({total / 60:.1f} min) en {dt / 60:.1f} min de codificación')


# ---------------------------------------------------------------------------------------------- programa
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('paso', choices=['escenas', 'linea', 'componer', 'render', 'audio', 'final', 'todo'])
    ap.add_argument('proyecto', nargs='?')
    ap.add_argument('--grabaciones')
    ap.add_argument('--voces')
    ap.add_argument('--trabajo', required=True)
    ap.add_argument('--salida')
    ap.add_argument('--bloques', help='solo estos bloques (ids separados por comas)')
    ap.add_argument('--solo', help='escenas: solo estas')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--formato', default='jpg', choices=['jpg', 'png'], help='fotogramas de las grabaciones para HyperFrames')
    ap.add_argument('--bitrate', default='12M')
    ap.add_argument('--forzar', action='store_true')
    ap.add_argument('--capitulos-comun', action='store_true', help='escribe también capitulos.txt junto a la salida')
    ap.add_argument('--borrar-bloques', action='store_true', help='final: borra los bloques renderizados al terminar')
    a = ap.parse_args()
    Path(a.trabajo).mkdir(parents=True, exist_ok=True)
    pasos = ['escenas', 'linea', 'componer', 'render', 'audio', 'final'] if a.paso == 'todo' else [a.paso]
    for p in pasos:
        print(f'== {p}')
        if p == 'escenas':
            paso_escenas(a)
        elif p == 'linea':
            paso_linea(a)
        elif p == 'componer':
            componer(a)
        elif p == 'render':
            paso_render(a)
        elif p == 'audio':
            paso_audio(a)
        elif p == 'final':
            paso_final(a)
            if a.borrar_bloques:
                shutil.rmtree(Path(a.trabajo) / 'bloques', ignore_errors=True)


if __name__ == '__main__':
    main()
