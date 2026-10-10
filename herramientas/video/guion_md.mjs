// Genera docs/video/guion.md a partir del proyecto del vídeo (docs/video/recorrido.json).
//   node herramientas/video/guion_md.mjs docs/video/recorrido.json docs/video/guion.md [informe del montaje]
// Con el informe del montaje (<salida>.informe.json) pone las duraciones reales de cada pieza.
import { readFileSync, writeFileSync } from 'node:fs'
const [, , ENTRADA, SALIDA, INFORME] = process.argv
const g = JSON.parse(readFileSync(ENTRADA, 'utf8'))
const inf = INFORME ? JSON.parse(readFileSync(INFORME, 'utf8')) : null
const real = new Map((inf?.piezas ?? []).map((p) => [p.id, p]))
const L = []
const w = (s = '') => L.push(s)
const mmss = (s) => { const t = Math.round(s); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}` }
const cod = (s) => '`' + String(s).replace(/`/g, "'") + '`'
const seg = (ms) => `${Math.round(ms / 1000)} s`
const esc = (p) => p.escena ?? p
const idDe = (p) => esc(p).id
const durDe = (p) => real.get(idDe(p))?.duracion ?? esc(p).duracion_estimada_s ?? 0
const palabras = g.piezas.filter((p) => !p.omitir).flatMap((p) => esc(p).narracion ?? []).map((n) => n.texto).join(' ').split(/\s+/).filter(Boolean).length

function accion(a) {
  const extra = []
  if (a.dentro) extra.push(`dentro de ${cod(a.dentro)}`)
  if (a.marco) extra.push('en el panel de la app (iframe)')
  const ex = extra.length ? ` (${extra.join(', ')})` : ''
  const acel = a.acelerar ? `; se acelera con el rótulo «${a.acelerar}»` : ''
  if (a.marca) return `**[${a.marca}]** empieza el fragmento de voz «${a.marca}»`
  if (a.esperarVoz) return 'espera a que termine la voz del narrador (para que no se pise con lo que se oye después)'
  if (a.microfono) return 'el micrófono empieza a «oír» su audio'
  if (a.ir) return `va a ${cod(a.ir)}`
  if (a.subir) return `sube ${cod(a.subir)} con ${a.clic ? cod(a.clic) : `«${a.clicTexto}»`}`
  if (a.clic) return `clic en ${cod(a.clic)}${ex}`
  if (a.clicTexto) return `clic en «${a.clicTexto}»${ex}`
  if (a.hover) return `pasa el cursor por ${cod(a.hover)}`
  if (a.hoverTexto) return `pasa el cursor por «${a.hoverTexto}»`
  // Los saltos de línea del texto tecleado se escriben como « ⏎ » para no romper la lista de Markdown.
  if (a.escribir) return `teclea «${a.escribir[1].includes('{contrasena}') ? 'la contraseña (campo password)' : a.escribir[1].replace(/\n+/g, ' ⏎ ')}» en ${cod(a.escribir[0])}${a.limpiar ? ' (borrando lo que había)' : ''}${ex}`
  if (a.tecla) return `tecla ${a.tecla}`
  if (a.seleccionar) return `elige «${a.seleccionar[1]}» en ${cod(a.seleccionar[0])}`
  if (a.esperar) return `pausa de ${(a.esperar / 1000).toFixed(1).replace('.', ',')} s${a.nota ? ` (${a.nota})` : ''}${acel}`
  if (a.esperarTexto) return `espera a que salga «${a.esperarTexto}» (máx. ${seg(a.max ?? 30000)}${acel})${ex}`
  if (a.esperarSinTexto) return `espera a que desaparezca «${a.esperarSinTexto}» (máx. ${seg(a.max ?? 30000)}${acel})`
  if (a.esperarSelector) return `espera ${cod(a.esperarSelector)} (máx. ${seg(a.max ?? 30000)}${acel})${ex}`
  if (a.esperarJs) return `espera a que se cumpla una condición en la página (respuesta terminada; máx. ${seg(a.max ?? 30000)}${acel})`
  if (a.mantenerMicro) return `mantiene pulsado ${cod(a.mantenerMicro[0])} mientras el micrófono dice su audio${acel}`
  if (a.scroll !== undefined) return typeof a.scroll === 'string' ? `desplaza hasta ${cod(a.scroll)}` : `desplaza ${a.scroll > 0 ? 'abajo' : 'arriba'} ${Math.abs(a.scroll)} px`
  const nota = a.nota ? ` con la nota ${a.nota.includes('«') ? a.nota : `«${a.nota}»`}` : ''
  if (a.resaltar) return `resalta ${cod(a.resaltar)}${nota}`
  if (a.resaltarTexto) return `resalta «${a.resaltarTexto}»${a.cerca ? ` (su ${cod(a.cerca)})` : ''}${nota}`
  if (a.eval) return 'marca por JS la opción correcta (ver el JSON)'
  return cod(JSON.stringify(a))
}

const total = inf?.duracion_s ?? g.piezas.filter((p) => !p.omitir).reduce((s, p) => s + durDe(p), 0)
w('# Guion del vídeo de CidIA')
w()
w(`Recorrido completo por la aplicación, pestaña a pestaña, con cada rol y con pruebas reales sobre los datos sintéticos de «Metalúrgica Arlanza, S. L.». Duración${inf ? '' : ' estimada'}: **${mmss(total)}** (${palabras} palabras de narración, voz ${g.voz.narrador}). Versión ${g.version}, ${g.fecha}. Hay también un resumen para el jurado (\`resumen.json\`, unos 3,7 minutos).`)
w()
w('Este documento se genera con `herramientas/video/guion_md.mjs` a partir de `docs/video/recorrido.json`, que es lo que leen las herramientas de `herramientas/video/` (grabador, voz y montaje). Cada escena dice qué cuenta y a qué punto de las bases del V DESAFÍO industrial responde; las acciones son clics y textos que existen en la interfaz desplegada, grabada con cada rol el 10 de octubre de 2026 en el servidor de pruebas (`' + g.servidor + '`). Cómo se hizo y cómo repetirlo: `04_VIDEO/LEEME.md` y `herramientas/video/README.md`.')
w()
w('## Resumen por capítulos')
w()
w('| Capítulo | Empieza | Duración | Quién | Qué se ve | Bases |')
w('|---|---|---|---|---|---|')
const caps = []
for (const p of g.piezas) {
  if (p.omitir) continue
  let c = caps.find((x) => x.nombre === p.capitulo)
  if (!c) caps.push((c = { nombre: p.capitulo, s: 0, ini: real.get(idDe(p))?.inicio_s, quien: new Set(), que: [], bases: new Set() }))
  const e = esc(p)
  c.s += durDe(p)
  if (p.escena) {
    c.quien.add(e.usuario ?? e.cuenta_acceso ?? (String(e.rol).startsWith('Invitado') ? 'invitado' : 'app'))
    c.que.push(e.titulo.split(' · ')[0])
    for (const b of (e.bases ?? '').replace(/^Bases: /, '').split(' · ')) if (b) c.bases.add(b)
  }
}
let acum = 0
for (const c of caps) {
  w(`| ${c.nombre} | ${mmss(c.ini ?? acum)} | ${mmss(c.s)} | ${[...c.quien].join(', ') || 'tarjetas'} | ${c.que.join('; ') || 'tarjetas con narración'} | ${[...c.bases].slice(0, 4).join('; ') || 'criterios de valoración'} |`)
  acum += c.s
}
w()
w('Criterios de valoración de las bases que se nombran en la voz y en los rótulos: cobertura funcional (40 %), adaptación a cada empresa (20 %), bajo coste (15 %), mejoras añadidas (15 %) y grado de innovación (10 %). Los puntos del alcance se citan con el nombre que les dan las bases (ver `docs/estado-mvp.md`).')
w()
w('## Antes de grabar')
w()
for (const p of g.preparacion) {
  w(`**${p.id}. ${p.que}.** ${p.como}`)
  w()
  w(`*Por qué:* ${p.por_que}${p.aviso ? ` **Aviso:** ${p.aviso}` : ''}`)
  w()
}
w('### Audios del micrófono')
w()
w('Chromium los «oye» con `--use-file-for-fake-audio-capture` (el grabador lo pone con la clave `microfono` de cada escena). Se generan con `voz.py frase … --microfono` (con `--voz` y `--velocidad` si la tabla lo dice). En 05a y 06a la pregunta también se oye en el vídeo (`oir_microfono`).')
w()
w('| Audio | Texto | Voz | Escena |')
w('|---|---|---|---|')
for (const a of g.audios_microfono) w(`| ${cod(a.fichero)} | ${a.texto} | ${a.voz ?? 'kokoro:ef_dora'}${a.velocidad ? ` a ${String(a.velocidad).replace('.', ',')}` : ''} | ${a.usado_en}${a.nota ? `. ${a.nota}` : ''} |`)
w()
w('### Ficheros')
w()
for (const f of g.ficheros) {
  w(`${cod(f.ruta)}${f.nota ? `: ${f.nota}` : ''}`)
  w()
  w('```' + (f.ruta.endsWith('.py') ? 'python' : 'csv'))
  w(f.contenido.trimEnd())
  w('```')
  w()
}
w('### Comprobación de las preguntas (P7)')
w()
w('El servidor de pruebas usa modelos diminutos (qwen3:0.6b): la misma pregunta puede salir bien o mal. Conviene lanzarlas justo antes de grabar (`POST /api/consulta/simple`, con el modo y el contexto indicados).')
w()
w('| Escena | Cuenta | Modo | Pregunta | Debe contener |')
w('|---|---|---|---|---|')
for (const c of g.comprobaciones_previas) w(`| ${c.escena} | ${c.usuario} | ${c.modo}${c.contexto ? ' (con tarea y paso)' : ''} | ${c.pregunta} | ${c.debe_contener.map((x) => `«${x}»`).join(', ')} |`)
w()
w('### Orden de grabación')
w()
w(g.motivo_orden)
w()
w(g.orden_grabacion.map((x, i) => `${i + 1}. ${x}`).join('\n'))
w()
w('## Escenas')
w()
w('Convenciones: ' + Object.values(g.convenciones).join(' '))
w()
let capActual = null
for (const p of g.piezas) {
  if (p.capitulo !== capActual) { capActual = p.capitulo; w(`### ${capActual}`); w() }
  const e = esc(p)
  const d = real.get(e.id)
  if (p.tipo === 'tarjeta') {
    w(`#### ${e.id} · tarjeta «${e.titulo}» (${(d?.duracion ?? e.duracion_estimada_s ?? 0).toFixed(1).replace('.', ',')} s)`)
    w()
    w(`Etiqueta: «${e.etiqueta}». Subtítulo: «${e.subtitulo}».`)
    w()
    for (const n of e.narracion ?? []) w(`> ${n.texto}`)
    if (e.narracion?.length) w()
    continue
  }
  w(`#### ${e.id} · ${e.titulo}${p.omitir ? ' (fuera del vídeo)' : ''}`)
  w()
  w(`* **Quién:** ${e.rol}${e.usuario ? ` · cuenta ${cod(e.usuario)}` : ''}${e.cuenta_acceso ? ` · entra con ${cod(e.cuenta_acceso)}` : ''}`)
  w(`* **Dónde:** ${e.contexto === 'app' ? 'app de escritorio (CDP en el puerto 9333)' : `navegador, ruta ${cod(e.ruta)}`}${e.microfono ? ` · micrófono: ${cod(e.microfono)}` : ''}`)
  w(`* **Rótulo:** «${e.titulo}» · «${e.bases}»`)
  const montaje = d ? ` · **en el vídeo:** ${d.duracion.toFixed(1).replace('.', ',')} s desde ${mmss(d.inicio_s)}${d.plan?.acelerado?.length ? `, esperas aceleradas ×${d.plan.acelerado.map((x) => Math.round(x)).join(', ×')}` : ''}${d.plan?.recortado_s ? `, ${String(d.plan.recortado_s).replace('.', ',')} s recortados` : ''}${d.plan?.congelado_s ? `, ${String(d.plan.congelado_s).replace('.', ',')} s congelados` : ''}` : ''
  w(`* **Duración estimada:** ${e.duracion_estimada_s ?? '?'} s${montaje}${e.depende_de ? ` · **depende de:** ${e.depende_de}` : ''}${e.preparacion ? ` · **preparación:** ${e.preparacion.join(', ')}` : ''}`)
  w()
  w('**Voz**')
  w()
  w(e.narracion.map((n) => `> ${n.marca ? `**[${n.marca}]** ` : ''}${n.texto}`).join('\n>\n'))
  w()
  w('**Acciones**')
  w()
  e.acciones.forEach((a, i) => w(`${i + 1}. ${accion(a)}`))
  w()
  const montajes = []
  if (e.recortes) montajes.push(`se recortan ${e.recortes.map(([a, b]) => `${a}-${b} s`).join(', ')} de la grabación`)
  for (const t of e.acelerar_tramos ?? []) {
    const cual = t.acciones
      ? (t.acciones[0] === t.acciones[1] ? `la acción ${t.acciones[0] + 1} va acelerada` : `las acciones ${t.acciones[0] + 1} a ${t.acciones[1] + 1} van aceleradas`)
      : `el tramo ${t.desde}-${t.hasta} s va acelerado`
    montajes.push(`${cual} ×${t.factor} con el rótulo «${t.etiqueta}»`)
  }
  if (montajes.length) { w(`**Montaje:** ${montajes.join('; ')}. ${e.notas_montaje ?? ''}`.trim()); w() }
  w(`**Comprobado:** ${e.verificado}`)
  w()
  if (e.notas) { w(`**Notas:** ${e.notas}`); w() }
}
w('## Incidencias encontradas al preparar y grabar el vídeo')
w()
for (const i of g.incidencias) w(`* **${i.id} (${i.estado ?? i.gravedad}).** ${i.que}${i.solucion ? ` ${i.solucion}` : ''}${i.propuesta ? ` *Propuesta:* ${i.propuesta}` : ''}`)
w()
w('## Cómo se usa con las herramientas')
w()
w('1. Voz: `python herramientas/video/voz.py narrar docs/video/recorrido.json --salida <voces>` y los audios del micrófono con `voz.py frase … --microfono`.')
w('2. Grabación, escena a escena y en el orden de grabación: `node herramientas/video/grabador.mjs docs/video/recorrido.json --solo <id> --salida <grabaciones> --voces <voces> --secretos <cidia.env>`. Las de la app de escritorio llevan `conectar` en la escena (la app abierta con `--remote-debugging-port=9333`).')
w('3. Montaje: `python herramientas/video/montaje.py docs/video/recorrido.json --grabaciones <grabaciones> --voces <voces> --salida 04_VIDEO/CidIA-recorrido-completo.mp4 --musica` (y lo mismo con `resumen.json` para el resumen).')
w('4. Revisar el informe del grabador de cada escena (fallos, consola, peticiones fallidas) y unos fotogramas; si una respuesta del modelo sale mal, repetir solo esa escena.')
w()
writeFileSync(SALIDA, L.join('\n'))
console.log('escrito', SALIDA, L.length, 'líneas')
