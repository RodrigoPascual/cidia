"""Guion v2 (por funcionalidades): comprueba el proyecto, calcula los tiempos y escribe el guion legible.

    python herramientas/video/guion_v2.py docs/video/v2/recorrido.json --grabaciones <carpeta> --voces <carpeta>
           [--resumen docs/video/v2/resumen.json] [--salida docs/video/v2/guion.md] [--renumerar]

* Comprueba que cada escena usa marcas que existen en su grabación, que los recortes y las aceleraciones caen dentro
  de la toma, que cada funcionalidad tiene tarjeta, demostración y resultado, y que ningún texto visible o hablado
  lleva rayas largas ni marcas que no deben salir.
* Calcula la línea de tiempo de cada escena con la misma función que el montaje (montaje.planificar): con la
  duración real de la narración si ya está sintetizada en --voces (voz.py narrar) o, si no, con una estimación
  (ajustada con las 118 frases de la v1: 0,0564 s por carácter dicho + 0,49 s por frase - 0,25 s).
* Escribe el guion legible (docs/video/v2/guion.md) con el mapa, cada funcionalidad con su patrón (tarjeta,
  demostración, resultado y bases), la cobertura de las bases, las tomas que faltan y los tiempos.
* --renumerar: vuelve a numerar las funcionalidades por orden entre las que entran en el montaje (sin «omitir») y
  rehace los textos que llevan el número (etiqueta, capítulo, subtítulo del mapa). Para cuando se grabe una toma
  que faltaba.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from comun import en_entorno  # noqa: E402

en_entorno(['PIL', 'numpy'])

import montaje  # noqa: E402
from voz import pronunciar, trocear  # noqa: E402

XF = montaje.XF
PROHIBIDAS = [re.compile(r'deep\s*seek', re.I)]
RAYA = chr(0x2014)  # raya larga: no debe salir en voz, rótulos ni documentos


# ---------------------------------------------------------------------------------------------- utilidades
def mmss(s: float) -> str:
    s = max(0, int(round(s)))
    return f'{s // 60}:{s % 60:02d}'


def estimar(texto: str) -> float:
    dicho = pronunciar(texto)
    frases = [f for f, _ in trocear(dicho, 0.32) if f]
    return max(0.6, 0.0564 * len(dicho) + 0.49 * len(frases) - 0.25)


def piezas_de(proyecto: dict, base: Path) -> list[dict]:
    """Todas las piezas (también las omitidas), con la escena en línea ya fusionada como hace comun.cargar_proyecto."""
    out = []
    for p in proyecto['piezas']:
        if isinstance(p.get('escena'), dict):
            out.append({**p['escena'], **{k: v for k, v in p.items() if k not in ('escena', 'tipo')}, 'tipo': 'escena', '_dir': base})
        else:
            out.append({**p, 'tipo': p.get('tipo', 'tarjeta'), '_dir': base})
    return out


def voz_de(p: dict, voces: Path | None) -> tuple[dict, bool]:
    """Fragmentos con duración: los sintetizados si coinciden con el texto, o estimados."""
    frs = p.get('narracion') or []
    ref = p.get('voz_de') or {}  # la voz de otra pieza (por ejemplo, un trozo de una toma en el resumen)
    indice = (voces / f"{ref.get('id', p['id'])}.json") if voces else None
    medida = None
    if indice and indice.exists():
        d = json.loads(indice.read_text(encoding='utf-8'))
        if ref.get('fragmentos'):
            d = {**d, 'fragmentos': [d['fragmentos'][n - 1] for n in ref['fragmentos']]}
        if [f['texto'] for f in d.get('fragmentos', [])] == [f['texto'] for f in frs]:
            medida = d
    out = []
    for n, fr in enumerate(frs, 1):
        dur = medida['fragmentos'][n - 1]['duracion'] if medida else estimar(fr['texto'])
        out.append({'n': n, 'texto': fr['texto'], 'marca': fr.get('marca'), 'tras': fr.get('tras', 0), 'duracion': dur,
                    'wav': (medida['fragmentos'][n - 1]['wav'] if medida else '')})
    return {'fragmentos': out}, bool(medida) or not frs


def plan_tarjeta(p: dict, voz: dict) -> dict:
    t = float(p.get('inicio_voz_s', 0.8))
    colocados = []
    for fr in voz['fragmentos']:
        colocados.append({'ini': t, 'fin': t + fr['duracion'], 'texto': fr['texto'], 'n': fr['n']})
        t += fr['duracion'] + float(fr.get('tras') or 0.35)
    fin_voz = colocados[-1]['fin'] if colocados else 0
    return {'duracion': round(max(float(p.get('duracion_s', 3.2)), fin_voz + 1.0), 3), 'voz': colocados, 'congelado_s': 0}


_SELECTORES = [  # cómo se llama en el guion lo que señala un selector sin nota
    (r'\.ins-medios', 'la imagen y el clip del paso'), (r'input\.ins-titulo-paso', 'el título del paso'),
    (r'\.doc-pregunta button', '«Buscar»'), (r'\.ev-opcion-editable\.correcta', 'la opción que la IA marcó como correcta'),
    (r'\.ev-editable\.propuesta$', 'la pregunta propuesta'), (r'\.ins-lista-confirmar', 'la lista de lo que pasará al publicar'),
    (r'\.consola-entrada', 'la línea de órdenes'),
    (r'\.burbuja\.asistente', 'la respuesta'), (r'\.sin-respaldo', 'el aviso «No lo he encontrado»'),
    (r"panelList", 'la lista de secciones de la app'), (r'\.ins-pasos li:nth-child\((\d)\)', 'el paso {0}'),
    (r'\.ins-pasos', 'la lista de pasos'), (r'\.ins-interruptor:nth-child\(2\)', 'el interruptor «seguridad»'),
    (r'\.ins-interruptores', 'los interruptores de paso crítico y de seguridad'), (r'\.ini-cifras', 'las cifras de la planta'),
    (r'table thead', 'las columnas de la tabla'), (r'\.doc-subida', 'el panel de subida'), (r'\.copiloto \.interruptor', 'el interruptor «Modo socrático»'),
    (r'\.boton-microfono', 'el micrófono'), (r'\.fuente\.citada', 'la fuente citada'), (r'\.pt-tarjeta', 'la tarea de la brida B'),
    (r'\.ej-columna:last-child', 'la respuesta del copiloto en el paso'), (r'\.ej-casilla', 'la casilla del punto crítico'),
    (r'\.ej-comparar', 'la foto junto a la de referencia'), (r'\.ev-paso\.critico', 'los pasos críticos'),
    (r'\.ev-boton-marca\.bien', '«Bien» en el siguiente paso'), (r'\.ev-opcion\[data-correcta\]', 'la opción correcta'),
    (r'\.ev-marca-correcta', 'la opción buena como correcta'), (r'\.ev-editable\.propuesta \.boton\.verde', '«Guardar y aprobar»'),
    (r'\.pp-fila\.activa', 'la fila de la brida B'), (r'\.mz-tabla', 'la matriz ILUO'), (r"mz-celda\[aria-label\^='([^·']+) · ([^']+)'", 'la celda de {0} en «{1}»'),
    (r'table tbody tr', 'el borrador de la tabla'), (r'\.zona-subida', 'la zona de subida'), (r'\.cap-via \.boton-voz', 'el micrófono de la nota de voz'),
    (r'\.modal \.cap-ficha-vista', 'la ficha propuesta'), (r'\.cap-detalles', 'la transcripción'), (r'\.cap-guion', 'el guion de la entrevista'),
    (r"Responder por voz", 'el micrófono de la respuesta'), (r'\.apo-revision', 'la aportación'), (r'\.consola', 'la salida de la consola'),
    (r'pre\.adm-json', 'la sentencia xAPI'), (r'^main$', 'la página'), (r'^table$', 'la tabla'), (r'\.usuario-enlace', 'su nombre, al pie de la barra'),
    (r"aria-label='([^']+)'", '«{0}»'), (r'\.perfil-datos', 'sus datos'), (r'\.reglas-contrasena', 'las reglas de la contraseña'),
    (r'\.memoria-explicacion', 'la explicación de la memoria'), (r'\.recuerdos', 'los recuerdos'),
]


def nombre_selector(sel: str) -> str:
    for patron, nombre in _SELECTORES:
        m = re.search(patron, sel)
        if m:
            return nombre.format(*m.groups())
    return sel


def resumir_accion(a: dict) -> str | None:
    def q(x):
        return x if x.startswith('«') else f'«{x}»'
    if 'marca' in a:
        return None
    if 'clicTexto' in a:
        return f"pulsa {q(a['clicTexto'])}" + (f" (sube {Path(a['subir']).name})" if 'subir' in a else '')
    if 'subir' in a:
        return f"sube {Path(a['subir']).name}"
    if 'clic' in a:
        return f"pulsa {a.get('nota') or nombre_selector(a['clic'])}"
    if 'escribir' in a:
        t = a['escribir'][1]
        if '{contrasena' in t:
            return 'teclea la contraseña (se ven puntos)'
        t = t.replace('\n', ' ')
        return f"escribe {q(t if len(t) <= 70 else t[:67] + '...')}"
    if 'seleccionar' in a:
        return f"elige {q(a['seleccionar'][1])}"
    if 'resaltarTexto' in a:
        return f"resalta {q(a['resaltarTexto'])}" + (f" con la nota {q(a['nota'])}" if a.get('nota') else '')
    if 'resaltar' in a:
        return 'resalta ' + nombre_selector(a['resaltar']) + (f" con la nota {q(a['nota'])}" if a.get('nota') else '')
    if 'hoverTexto' in a:
        return f"pasa por {q(a['hoverTexto'])}"
    if 'hover' in a:
        return 'pasa el cursor por ' + nombre_selector(a['hover'])
    if 'mantenerMicro' in a:
        return 'mantiene pulsado el micrófono (habla el audio de la escena)'
    if 'microfono' in a:
        return None
    if 'esperarTexto' in a or 'esperarSelector' in a or 'esperarJs' in a or 'esperarSinTexto' in a:
        if 'esperarSinTexto' in a and a.get('acelerar') is False and a.get('max', 0) <= 2000:
            return f"comprueba que no aparece {q(a['esperarSinTexto'])}"
        if isinstance(a.get('acelerar'), str):
            return f"espera al servidor ({a['acelerar']}, acelerado)"
        return None
    if 'esperar' in a:
        return f"espera ({a['acelerar']}, acelerado)" if isinstance(a.get('acelerar'), str) else None
    if 'scroll' in a:
        return 'desplaza la página'
    if 'tecla' in a:
        return f"tecla {a['tecla']}"
    if 'eval' in a:
        return None  # p. ej. marcar qué opción es la correcta antes del clic: no se ve
    if 'esperarVoz' in a:
        return None
    if 'ir' in a:
        return f"va a {a['ir']}"
    return None


def json_compacto(d: dict) -> str:
    """Una clave por línea y una acción por línea: se lee y se copia al proyecto tal cual."""
    filas = []
    for k, v in d.items():
        if k == 'acciones':
            filas.append('  "acciones": [\n' + ',\n'.join('    ' + json.dumps(a, ensure_ascii=False) for a in v) + '\n  ]')
        else:
            filas.append(f'  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}')
    return '{\n' + ',\n'.join(filas) + '\n}'


def compactar(xs: list[str]) -> list[str]:
    """Junta repeticiones seguidas de 1 a 3 acciones: «pulsa «Bien» (×8)», «pulsa la opción correcta; pulsa «Siguiente» (×5)»."""
    out, i = [], 0
    while i < len(xs):
        mejor = (1, 1)
        for n in (1, 2, 3):
            k = 1
            while xs[i:i + n] == xs[i + k * n:i + (k + 1) * n] and len(xs[i + k * n:i + (k + 1) * n]) == n:
                k += 1
            if k > 1 and n * k > mejor[0] * mejor[1]:
                mejor = (n, k)
        n, k = mejor
        out.append('; '.join(xs[i:i + n]) + (f' (×{k})' if k > 1 else ''))
        i += n * k
    return out


def textos_visibles(p: dict) -> list[tuple[str, str]]:
    out = []
    for k in ('titulo', 'subtitulo', 'etiqueta', 'bases', 'nombre', 'rol', 'persona', 'para_que', 'texto_microfono'):
        if isinstance(p.get(k), str):
            out.append((k, p[k]))
    if isinstance(p.get('resultado'), str):
        out.append(('resultado', p['resultado']))
    if isinstance(p.get('resultado'), dict):
        out.append(('resultado', p['resultado'].get('texto', '')))
        out += [('resultado.bases', b) for b in p['resultado'].get('bases', [])]
    for b in p.get('bases', []) if isinstance(p.get('bases'), list) else []:
        out.append(('bases', b))
    for fr in p.get('narracion') or []:
        out.append(('narración', fr['texto']))
    for a in p.get('acciones') or []:
        if a.get('nota') and ('resaltar' in a or 'resaltarTexto' in a):
            out.append(('nota en pantalla', a['nota']))
    for c in p.get('criterios') or []:
        out.append(('criterio', c.get('texto', '')))
    for x in p.get('personas') or []:
        out.append(('persona', f"{x.get('nombre')} {x.get('papel')} {x.get('departamento')}"))
    return out


# ---------------------------------------------------------------------------------------------- renumerar
def renumerar(ruta: Path) -> None:
    proy = json.loads(ruta.read_text(encoding='utf-8'))
    cat = {f['id']: f for f in proy.get('funcionalidades', [])}
    bloques = {b['id']: b for b in proy.get('mapa', {}).get('bloques', [])}
    n = 0
    numeros = {}
    for p in proy['piezas']:
        if p.get('pieza') == 'funcionalidad' and not p.get('omitir'):
            n += 1
            numeros[p['funcionalidad']] = n
    for f in cat.values():
        f['numero'] = numeros.get(f['id'])
        if f['numero'] and f.get('estado') == 'requiere_grabacion':
            f['estado'] = 'grabada'  # su tarjeta ya entra en el montaje: se ha grabado
    for p in proy['piezas']:
        fid = p.get('funcionalidad')
        if p.get('pieza') == 'funcionalidad':
            p['numero'] = numeros.get(fid)
            pre = f"Funcionalidad {p['numero']}" if p['numero'] else 'Funcionalidad por grabar'
            p['etiqueta'] = f"{pre} · {p['bloque_nombre']} · {p['rol']}"
        if fid:
            nom = cat[fid]['nombre']
            p['capitulo'] = f"{numeros[fid]} · {nom}" if fid in numeros else f'Por grabar · {nom}'
    # Las vueltas al mapa van en el capítulo de la primera funcionalidad que entra de su bloque.
    for p in proy['piezas']:
        if p.get('pieza') == 'mapa' and p.get('destacar') in bloques:
            fs = [cat[x] for x in bloques[p['destacar']]['funcionalidades'] if x in numeros]
            p['subtitulo'] = ' · '.join(f"{numeros[f['id']]} {f['nombre']}" for f in fs)
            if fs:
                p['capitulo'] = f"{numeros[fs[0]['id']]} · {fs[0]['nombre']}"
    ruta.write_text(json.dumps(proy, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Renumerado {ruta}: {n} funcionalidades en el montaje')


# ---------------------------------------------------------------------------------------------- análisis
def analizar(ruta: Path, grabaciones: Path, voces: Path | None) -> dict:
    proy = json.loads(ruta.read_text(encoding='utf-8'))
    piezas = piezas_de(proy, ruta.parent)
    a = SimpleNamespace(voces=str(voces or grabaciones))
    problemas, avisos, filas = [], [], []
    medidas = True
    t = 0.0
    for p in piezas:
        pid = p['id']
        fila = {'p': p, 'id': pid, 'omitir': bool(p.get('omitir'))}
        for campo, texto in textos_visibles(p):
            if RAYA in texto:
                problemas.append(f'{pid}: raya larga en {campo}: {texto[:60]}')
            if any(r.search(texto) for r in PROHIBIDAS):
                problemas.append(f'{pid}: marca prohibida en {campo}')
        voz, medida = voz_de(p, voces)
        if p.get('omitir'):
            fila['plan'] = None
            fila['estimada'] = sum(f['duracion'] for f in voz['fragmentos'])
            filas.append(fila)
            continue
        medidas &= medida
        if p['tipo'] == 'escena':
            inf_f = grabaciones / f"{p.get('grabacion', pid)}.json"
            if not inf_f.exists():
                problemas.append(f'{pid}: falta la grabación ({inf_f.name})')
                filas.append(fila)
                continue
            inf = json.loads(inf_f.read_text(encoding='utf-8'))
            if p.get('hasta_accion') is not None:
                inf = montaje.informe_hasta(inf, int(p['hasta_accion']), float(p.get('cola_accion_s', 0.9)))
            marcas = {m['nombre'] for m in inf.get('marcas', [])}
            for fr in p.get('narracion') or []:
                if fr.get('marca') and fr['marca'] not in marcas:
                    problemas.append(f"{pid}: la marca «{fr['marca']}» no está en la grabación")
            D = inf['duracion_ms'] / 1000
            for r in p.get('recortes', []):
                if not (0 <= r[0] < r[1] <= D):
                    problemas.append(f'{pid}: recorte {r} fuera de la toma ({D:.1f} s)')
            for tr in p.get('acelerar_tramos', []):
                if 'acciones' in tr and not (0 <= tr['acciones'][0] <= tr['acciones'][1] < len(inf.get('acciones', []))):
                    problemas.append(f'{pid}: acelerar_tramos fuera de las acciones del informe')
            res = p.get('resultado')
            if isinstance(res, dict) and not (1 <= int(res.get('desde_fragmento', 0)) <= len(p.get('narracion') or [])):
                problemas.append(f'{pid}: resultado.desde_fragmento fuera de la narración')
            plan = montaje.planificar(p, inf, voz, a)
            plan['grabado_s'] = D
            fila['plan'] = plan
            for av in plan['avisos']:
                problemas.append(f'{pid}: {av}')
            if plan['congelado_s'] > 3.2:
                avisos.append(f"{pid}: {plan['congelado_s']:.1f} s de imagen congelada (la voz es más larga que la imagen)")
        else:
            fila['plan'] = plan_tarjeta(p, voz)
        fila['inicio'] = t
        t += fila['plan']['duracion'] - XF
        filas.append(fila)
    total = t + XF if filas else 0
    # Patrón de cada funcionalidad: tarjeta, al menos una escena y resultado en la última.
    cat = {f['id']: f for f in proy.get('funcionalidades', [])}
    for fid, f in cat.items():
        tarjetas = [x for x in piezas if x.get('pieza') == 'funcionalidad' and x.get('funcionalidad') == fid]
        escs = [x for x in piezas if x['tipo'] == 'escena' and x.get('funcionalidad') == fid and not x.get('omitir')]
        if not tarjetas:
            problemas.append(f'{fid}: sin tarjeta')
        if f.get('estado') != 'requiere_grabacion':
            if not escs:
                problemas.append(f'{fid}: sin escena en el montaje')
            elif not isinstance(escs[-1].get('resultado'), dict):
                problemas.append(f'{fid}: la última escena ({escs[-1]["id"]}) no lleva «resultado»')
    return {'proyecto': proy, 'filas': filas, 'total': total, 'problemas': problemas, 'avisos': avisos, 'medidas': medidas}


# ---------------------------------------------------------------------------------------------- guion legible
def guion_md(A: dict, R: dict | None, ruta_proy: Path) -> str:
    proy, filas = A['proyecto'], A['filas']
    cat = {f['id']: f for f in proy.get('funcionalidades', [])}
    bloques = proy.get('mapa', {}).get('bloques', [])
    por_id = {f['id']: f for f in filas}
    escenas_de = {}
    for f in filas:
        if f['p']['tipo'] == 'escena' and f['p'].get('funcionalidad'):
            escenas_de.setdefault(f['p']['funcionalidad'], []).append(f)
    tarjeta_de = {f['p']['funcionalidad']: f for f in filas if f['p'].get('pieza') == 'funcionalidad'}
    voz_proy = (proy.get('voz') or {}).get('narrador', '')
    origen = (f'medidas con la narración ya sintetizada ({voz_proy}; si cambia la voz, se vuelve a sintetizar y a ejecutar este guion)'
              if A['medidas'] else 'estimadas a partir del texto (aún sin sintetizar)')
    L = []
    w = L.append
    w('# Guion v2 de CidIA · recorrido sistemático por funcionalidades')
    w('')
    w(f"Generado con `herramientas/video/guion_v2.py` a partir de `{ruta_proy.as_posix().split('cidia/')[-1]}` y de los informes de las tomas de `--grabaciones`. "
      f"Duraciones {origen}. Fecha del guion: {proy.get('fecha', '')}.")
    w('')
    n_func = sum(1 for f in cat.values() if f.get('numero'))
    n_pend = sum(1 for f in cat.values() if not f.get('numero'))
    w(f"**Vídeo completo: {mmss(A['total'])}** ({A['total']:.0f} s) con {n_func} funcionalidades grabadas"
      + (f" · **resumen: {mmss(R['total'])}** ({R['total']:.0f} s)" if R else '') + (f'. Falta 1 por grabar (sección 6).' if n_pend == 1 else f'. Faltan {n_pend} por grabar (sección 6).'))
    w('')
    w('Son los tiempos del guion (escenas y voz). El vídeo montado dura más, porque las tarjetas de funcionalidad se alargan '
      'para que se puedan leer y el panel de resultado no tapa la última acción: las duraciones reales están en '
      '`04_VIDEO/v2/final/*.informe.json` y en los capítulos (nota del apartado 8).')
    w('')
    w('## 1. La idea')
    w('')
    w('El vídeo enseña todas las funcionalidades de CidIA con el mismo patrón, para que el jurado sepa siempre dónde está y para qué sirve lo que ve:')
    w('')
    w('1. **Tarjeta «Funcionalidad N · nombre»** con quién la usa (rol y persona del ejemplo).')
    w('2. **Para qué sirve en la planta**, en una frase, dicha sobre la tarjeta.')
    w('3. **Demostración real** con Metalúrgica Arlanza: solo acciones que están en las tomas grabadas el 10/10, con sus tiempos.')
    w('4. **Resultado** en una frase y, en un panel, los **puntos de las bases** que cubre.')
    w('')
    w('Empieza con el problema, el ejemplo (la empresa ficticia y su gente) y un **mapa de funcionalidades** organizado por el ciclo que piden las bases: capturar, estructurar, formar, acompañar, evaluar y certificar, con el acceso delante y la administración debajo. Antes de cada bloque se vuelve al mapa con ese bloque encendido. El cierre repasa los cinco criterios (40, 20, 15, 15 y 10 %), la implantación y las licencias.')
    w('')
    w('Por qué así (decidido sin preguntar, como se pidió):')
    w('')
    w('* **Por el ciclo de las bases y no por pantallas.** El 40 % de la nota es cobertura funcional y las bases describen un ciclo; ordenar por ese ciclo deja ver que no falta ningún paso. Las pantallas de la app ya se ven dentro de cada funcionalidad.')
    w('* **Una funcionalidad, una idea.** Cada tarjeta responde a una pregunta del jurado («¿quién lo usa?, ¿para qué?») y cada resultado, a «¿y qué gano?». El rótulo de bases sale al final, cuando ya se ha visto la prueba.')
    w('* **Mismo ejemplo de principio a fin.** La brida B (IT-023) y la prensa 3 (IT-031) atraviesan todo el ciclo: Carmen captura, Lucía aprende y la ejecuta, Javier evalúa y certifica. Los errores reales de los modelos se enseñan y se corrigen en pantalla.')
    w('* **Más corto que la v1 sin perder nada.** La narración es más breve y concreta; los ratos en que el grabador esperó a la voz larga de la v1 se recortan (pantalla quieta), las esperas del servidor se aceleran con su rótulo como en la v1, los clics repetidos (las seis respuestas del cuestionario y los ocho pasos de la observación) van a ×3 y el tecleo de las preguntas a ×2, siempre con su rótulo. Nada se acelera ni se corta sin avisar, salvo ratos con la pantalla quieta.')
    w('* **Compatible.** El proyecto se monta ya con `montaje.py` (tarjetas sencillas). El montaje v2 usa los campos nuevos para el diseño nuevo: mapa, tarjeta de funcionalidad, panel de resultado con bases, criterios.')
    w('')
    w('## 2. Mapa de funcionalidades')
    w('')
    w('| Bloque | N | Funcionalidad | Quién la usa | Tomas | Estado |')
    w('|---|---|---|---|---|---|')
    for b in bloques:
        for fid in b['funcionalidades']:
            f = cat[fid]
            est = {'grabada': 'grabada', 'requiere_grabacion': '**requiere grabación**'}.get(f['estado'], f['estado'])
            if f.get('regrabar'):
                est += ' (mejorable: ver 6)'
            w(f"| {b['orden']} · {b['verbo']} | {f.get('numero') or '-'} | {f['nombre']} | {f['rol']} | {', '.join(f['escenas'])} | {est} |")
    w('')
    w('## 3. Escaleta y tiempos')
    w('')
    w('| Empieza | Pieza | Qué es | Dura | Ajustes |')
    w('|---|---|---|---|---|')
    for f in filas:
        if f['omitir'] or not f.get('plan'):
            continue
        p, pl = f['p'], f['plan']
        que = p.get('pieza') or 'escena'
        if que == 'funcionalidad':
            que = f"tarjeta: {p.get('titulo')}"
        elif que == 'mapa':
            que = 'mapa' + (f" ({p.get('destacar')})" if p.get('destacar') else '')
        elif que == 'escena':
            que = p.get('titulo', '')
        aj = []
        if pl.get('congelado_s'):
            aj.append(f"congela {pl['congelado_s']:.1f} s")
        if pl.get('recortado_s'):
            aj.append(f"recorta {pl['recortado_s']:.1f} s")
        if pl.get('acelerado'):
            aj.append('acelera ' + ', '.join(f'×{x:.0f}' for x in pl['acelerado']))
        w(f"| {mmss(f['inicio'])} | `{f['id']}` | {que} | {pl['duracion']:.1f} s | {'; '.join(aj)} |")
    w('')
    w('## 4. Guion pieza a pieza')
    w('')

    def narr(f, absoluto=True):
        pl = f['plan']
        out = []
        if pl:
            for c in sorted(pl['voz'], key=lambda c: c['ini']):
                if c.get('microfono'):
                    out.append(f"* `{mmss(f['inicio'] + c['ini'])}` (se oye el micrófono) {c['texto']}")
                    continue
                fr = (f['p'].get('narracion') or [])[c['n'] - 1]
                mk = f" [{fr['marca']}]" if fr.get('marca') else ''
                extra = ' **(resultado)**' if isinstance(f['p'].get('resultado'), dict) and c['n'] >= f['p']['resultado']['desde_fragmento'] else ''
                out.append(f"* `{mmss(f['inicio'] + c['ini'])}`{mk}{extra} {c['texto']}")
        else:
            for fr in f['p'].get('narracion') or []:
                mk = f" [{fr['marca']}]" if fr.get('marca') else ''
                out.append(f"*{mk} {fr['texto']}")
        return out

    def bloque_escena(f):
        p = f['p']
        pl = f.get('plan')
        cab = f"**Escena `{p['id']}`** · {p.get('titulo', '')}"
        if pl:
            cab += f" · {pl['duracion']:.1f} s en el vídeo (toma de {pl['grabado_s']:.0f} s)"
        w(cab)
        w('')
        w(f"* Quién y dónde: {p.get('rol', p.get('usuario'))} · `{p.get('ruta') or 'app de escritorio'}`")
        acc = compactar([x for x in (resumir_accion(a) for a in p.get('acciones', [])) if x])
        if acc:
            w('* Qué se ve: ' + '; '.join(acc) + '.')
        if pl:
            aj = []
            for tr in p.get('recortes', []):
                aj.append(f'recorte {tr[0]}-{tr[1]} s')
            for tr in p.get('acelerar_tramos', []):
                aj.append(f"«{tr.get('etiqueta')}» ×{tr['factor']}")
            if p.get('espera_objetivo_s'):
                aj.append(f"esperas a {p['espera_objetivo_s']} s")
            if aj:
                w('* Montaje: ' + '; '.join(aj) + '.')
        if p.get('verificado'):
            w(f"* Comprobado: {p['verificado']}")
        w('* Narración:')
        for x in narr(f):
            w('  ' + x)
        if isinstance(p.get('resultado'), dict):
            r = p['resultado']
            w(f"* **Resultado** (panel desde el fragmento {r['desde_fragmento']}): {r['texto']}")
            w(f"* **Bases**: {' · '.join(r['bases'])}")
        w('')

    for f in filas:
        p = f['p']
        if f['omitir'] and p['tipo'] == 'escena':
            continue
        if f['omitir'] and p.get('pieza') == 'funcionalidad':
            continue
        pz = p.get('pieza')
        if pz == 'mapa':
            w(f"### Mapa · {p.get('etiqueta')}" + (f" · {mmss(f['inicio'])}" if f.get('plan') else ''))
            w('')
            w(f"*{p.get('titulo')}*" + (f": {p.get('subtitulo')}" if p.get('subtitulo') else ''))
            w('')
            for x in narr(f):
                w(x)
            w('')
        elif pz == 'funcionalidad':
            fd = cat[p['funcionalidad']]
            w(f"### {p.get('etiqueta')} · {mmss(f['inicio'])}")
            w('')
            w(f"**{fd['nombre']}** · {fd['persona']}")
            w('')
            w(f"* Para qué sirve: {fd['para_que']}")
            w(f"* Tarjeta ({f['plan']['duracion']:.1f} s):")
            for x in narr(f):
                w('  ' + x)
            w('')
            for fe in escenas_de.get(p['funcionalidad'], []):
                if not fe['omitir']:
                    bloque_escena(fe)
            susts = [fe for fe in escenas_de.get(p['funcionalidad'], []) if fe['omitir']]
            for fe in susts:
                if fe['p'].get('sustituida_por'):
                    w(f"*Toma antigua `{fe['id']}`, sustituida por `{fe['p']['sustituida_por']}` (fuera del montaje).*")
                elif fe['p'].get('opcional'):
                    narr_op = ' '.join(fr['texto'] for fr in fe['p'].get('narracion') or [])
                    w(f"*Escena opcional `{fe['id']}` ({fe['p'].get('titulo', '')}), grabada pero fuera del montaje: {fe['p'].get('motivo', '')} Narración: «{narr_op}»*")
                else:
                    w(f"*Toma por grabar `{fe['id']}`" + (f" (sustituye a {', '.join(fe['p'].get('sustituye', []))})" if fe['p'].get('sustituye') else '') + ': ver sección 6.*')
                w('')
        elif p['tipo'] == 'tarjeta':
            w(f"### {p.get('etiqueta') or p.get('pieza')} · {mmss(f['inicio'])}" if f.get('plan') else f"### {p.get('etiqueta')}")
            w('')
            w(f"*{p.get('titulo')}*" + (f": {p.get('subtitulo')}" if p.get('subtitulo') else ''))
            w('')
            for x in narr(f):
                w(x)
            w('')
        elif p['tipo'] == 'escena' and not p.get('funcionalidad'):
            bloque_escena(f)

    w('## 5. Cobertura de las bases')
    w('')
    w('Punto por punto del alcance (`docs/estado-mvp.md`: ✓ funciona de punta a punta, ◐ simplificado, ○ preparado sin probar en el equipo real) y dónde se ve en el vídeo.')
    w('')
    w('| Bloque de las bases | Punto | Estado | Funcionalidades (N) | Escenas |')
    w('|---|---|---|---|---|')
    for c in proy.get('cobertura_bases', []):
        fs = [cat[x] for x in c['funcionalidades']]
        nombres = ', '.join(f"{x['nombre']} ({x.get('numero') or 'por grabar'})" for x in fs)
        escs = sorted({e for x in fs for e in x['escenas'] if not any(fl['id'] == e and fl['omitir'] for fl in filas)})
        w(f"| {c['bloque']} | {c['punto']} | {c['estado']} | {nombres} | {', '.join(escs)} |")
    w('')
    w('Criterios de valoración y qué los demuestra:')
    w('')
    for c in proy.get('criterios', []):
        w(f"* **{c['peso']} % · {c['nombre']}**: {c['texto']} Funcionalidades: {', '.join(cat[x]['nombre'] for x in c['funcionalidades'])}.")
    w('')
    w('## 6. Tomas que requieren grabación')
    w('')
    w('Todas con datos recién sembrados (P1). Hasta grabarlas, van en el proyecto con `"omitir": true` y el vídeo usa las tomas de la v1. El grabador y `voz.py` se saltan las piezas omitidas, así que cada toma está también como escena suelta en `docs/video/v2/tomas-por-grabar/` (copias que escribe `guion_v2.py --extraer-tomas`; la fuente es la pieza de `recorrido.json`):')
    w('')
    w('```powershell')
    w('python herramientas\\video\\voz.py narrar docs\\video\\v2\\tomas-por-grabar\\02e-perfil-lucia.json --salida $V2\\voces')
    w('node herramientas\\video\\grabador.mjs docs\\video\\v2\\tomas-por-grabar\\02e-perfil-lucia.json --salida $V2\\grabaciones --voces $V2\\voces --secretos <fichero de secretos>')
    w('```')
    w('')
    w('Con la toma buena: quitar su `omitir` en `recorrido.json`, poner `"omitir": true` en las piezas de `sustituye`, ajustar los recortes al informe nuevo (y montar con `--grabaciones` apuntando a una carpeta que tenga las tomas viejas y las nuevas) y ejecutar `guion_v2.py --renumerar` si entra una funcionalidad nueva.')
    w('')
    for pend in proy.get('pendientes_grabacion', []):
        f = por_id.get(pend['id'])
        if not f:
            continue
        p = f['p']
        w(f"### `{pend['id']}` · {pend['que']}")
        w('')
        fd = cat.get(pend['funcionalidad'])
        if fd:
            w(f"* Funcionalidad: {fd['nombre']} ({fd['rol']}).")
        if pend.get('sustituye'):
            w(f"* Sustituye a: {', '.join(pend['sustituye'])}.")
        for x in p.get('preparacion', []) if isinstance(p.get('preparacion'), list) else []:
            w(f'* Preparación: {x}')
        if p.get('verificado'):
            w(f"* Estado: {p['verificado']}")
        if p.get('notas'):
            w(f"* Notas: {p['notas']}")
        w(f"* Narración prevista (unos {f.get('estimada', 0):.0f} s de voz):")
        for x in narr(f):
            w('  ' + x)
        esc = {k: v for k, v in p.items() if k not in ('narracion', '_dir', 'tipo', 'capitulo', 'funcionalidad', 'omitir',
                                                     'requiere_grabacion', 'sustituye', 'verificado', 'notas', 'preparacion', 'resultado')}
        w('')
        w('```json')
        w(json_compacto(esc))
        w('```')
        w('')
    w('Sin toma y sin formato de grabador (fuera del navegador): la instalación de `CidIA-Setup.exe` en un portátil y la de `instalar-servidor.sh`. Se cuentan en la tarjeta de implantación del cierre; si se quieren enseñar, grabar la pantalla de Windows con ffmpeg (gdigrab) y la terminal del servidor en modo comprobación, unos 10 s cada una, y añadirlas como escenas antes de `cierre-implantacion`.')
    w('')
    if R:
        w('## 7. Resumen para el jurado')
        w('')
        w(f"`docs/video/v2/resumen.json`, **{mmss(R['total'])}**: el mismo patrón con una funcionalidad de cada paso del ciclo. Comparte grabaciones, ids y narración con el completo (mismas voces); solo `r-mapa` es propia.")
        w('')
        w('| Empieza | Pieza | Dura |')
        w('|---|---|---|')
        for f in R['filas']:
            if f['omitir'] or not f.get('plan'):
                continue
            p = f['p']
            nombre = p.get('titulo') if p['tipo'] == 'escena' else (p.get('etiqueta') or p.get('pieza'))
            w(f"| {mmss(f['inicio'])} | `{f['id']}` · {nombre} | {f['plan']['duracion']:.1f} s |")
        w('')
    w('## 8. Cómo se monta')
    w('')
    w('Desde `cidia/`, con las tomas de `04_VIDEO/material-v3` y la voz final en `04_VIDEO/v2/voces-final` (montaje v2 con HyperFrames; detalle en `herramientas/video/README.md`, apartado 10, y en `04_VIDEO/v2/final/LEEME.md`):')
    w('')
    w('```powershell')
    w(r'$M = (Resolve-Path "..\04_VIDEO\material-v3").Path; $V2 = (Resolve-Path "..\04_VIDEO\v2").Path')
    w(r'python herramientas\video\voz.py narrar docs\video\v2\recorrido.json --perfil v2 --semilla 1234 --salida $V2\voces-final')
    w(r'python herramientas\video\guion_v2.py docs\video\v2\recorrido.json --resumen docs\video\v2\resumen.json --grabaciones $M\grabaciones --voces $V2\voces-final')
    w(r'python herramientas\video\hyperframes.py todo docs\video\v2\recorrido.json --grabaciones $M\grabaciones --voces $V2\voces-final --trabajo $V2\trabajo\recorrido --salida $V2\final\CidIA-recorrido.mp4')
    w(r'python herramientas\video\hyperframes.py todo docs\video\v2\resumen.json --grabaciones $M\grabaciones --voces $V2\voces-final --trabajo $V2\trabajo\resumen --salida $V2\final\CidIA-resumen.mp4')
    w('```')
    w('')
    w('Las duraciones de este guion salen de `montaje.planificar` sin rampas ni recortes automáticos: el montaje v2 (`montaje.py --limpio`) añade rampas de 0,3 s a las aceleraciones y quita los ratos con la pantalla quieta y sin voz, así que sus escenas pueden durar unas décimas menos. Las tarjetas de funcionalidad del montaje v2 duran al menos 6,5 s (7,5 en el resumen) y lo que pida la lectura de su «para qué sirve» (palabras / 3 + 1 s), y una escena se alarga con su último fotograma si el panel de resultado no cabe después de la última acción: el recorrido montado dura unos 17 min y el resumen, unos 5.')
    w('')
    w('## 9. Si hay que acortar')
    w('')
    w('El objetivo es de 12 a 14 minutos para el completo y de 3 a 4 para el resumen. Si la voz definitiva es más lenta que la medida, estos recortes no quitan ninguna funcionalidad (en orden de preferencia):')
    w('')
    dur = {f['id']: f['plan']['duracion'] - XF for f in filas if f.get('plan') and not f['omitir']}
    voz_total = sum(c['fin'] - c['ini'] for f in filas if f.get('plan') and not f['omitir'] for c in f['plan']['voz'] if not c.get('microfono'))
    candidatos = [
        (['v2-reparto'], 'quitar la tarjeta de quién es quién (las personas ya salen en cada tarjeta de funcionalidad)'),
        (['12e-sistema-admin'], 'quitar el estado del servidor (el panel de resultado de la funcionalidad pasa a 12d)'),
        (['07a-itinerario-lucia'], 'quitar el itinerario y dejar solo la micro-lección (la tarjeta ya dice qué le falta)'),
        (['02c-jefe-javier', '02d-admin'], 'dejar solo a Lucía en «Cada rol ve lo suyo» y contar los otros roles en su narración'),
    ]
    for ids, que in candidatos:
        s = sum(dur.get(i, 0) for i in ids)
        if s:
            w(f'* {que}: unos {s:.0f} s (`{"`, `".join(ids)}`).')
    w(f'* Subir el narrador de 0,95 a 1,0: unos {voz_total * 0.05:.0f} s, repartidos (la voz suma {voz_total / 60:.1f} min).')
    w('')
    if A['problemas'] or A['avisos']:
        w('## 10. Avisos de la comprobación')
        w('')
        for x in A['problemas']:
            w(f'* Problema: {x}')
        for x in A['avisos']:
            w(f'* Aviso: {x}')
        w('')
    texto = '\n'.join(L) + '\n'
    return texto.replace(RAYA, '-')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('proyecto')
    ap.add_argument('--grabaciones', required=True)
    ap.add_argument('--voces')
    ap.add_argument('--resumen')
    ap.add_argument('--salida')
    ap.add_argument('--renumerar', action='store_true')
    ap.add_argument('--extraer-tomas', metavar='CARPETA',
                    help='escribe cada toma por grabar (pieza con «requiere_grabacion») como escena suelta, lista para grabador.mjs y voz.py')
    a = ap.parse_args()
    ruta = Path(a.proyecto).resolve()
    if a.renumerar:
        renumerar(ruta)
    if a.extraer_tomas:
        dest = Path(a.extraer_tomas)
        dest.mkdir(parents=True, exist_ok=True)
        for p in json.loads(ruta.read_text(encoding='utf-8'))['piezas']:
            e = p.get('escena')
            if isinstance(e, dict) and p.get('requiere_grabacion'):
                (dest / f"{e['id']}.json").write_text(json.dumps(e, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                print(f'Toma por grabar: {dest / (e["id"] + ".json")}')
    grab = Path(a.grabaciones).resolve()
    voces = Path(a.voces).resolve() if a.voces else None
    A = analizar(ruta, grab, voces)
    R = analizar(Path(a.resumen).resolve(), grab, voces) if a.resumen else None
    for nombre, X in (('completo', A), ('resumen', R)):
        if not X:
            continue
        print(f"{nombre}: {mmss(X['total'])} ({X['total']:.1f} s), duraciones {'medidas' if X['medidas'] else 'estimadas'}")
        for x in X['problemas']:
            print('  PROBLEMA', x)
        for x in X['avisos']:
            print('  aviso', x)
    salida = Path(a.salida) if a.salida else ruta.with_name('guion.md')
    salida.write_text(guion_md(A, R, ruta), encoding='utf-8')
    print(f'Guion: {salida}')
    if A['problemas'] or (R and R['problemas']):
        sys.exit(1)


if __name__ == '__main__':
    main()
