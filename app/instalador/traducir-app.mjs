// Castellano en el proceso principal de la app base (DeepSeek Harness 0.2.0-rc.2, MIT).
//
// La barra de menús de la ventana en Windows («Application», «Edit») no es un menú nativo: la
// pinta lib/preload-app.cjs con los textos de su diccionario, y los menús que se abren, la bandeja
// y los cuadros de diálogo salen de lib/main.js. Los dos solo traen inglés y chino (inglés para
// cualquier otro idioma), así que con CidIA en castellano todo eso salía en inglés y con la marca
// de la app base («About DeepSeek Harness», «Quit DeepSeek Harness?»). Este script, sobre la copia
// de la app que lleva el instalador de CidIA (nunca sobre otra):
//
//   1. añade a lib/main.js, lib/preload-app.cjs y lib/preload-welcome.cjs un diccionario 'es' con
//      los textos de textos/app-es.json (mismas claves y marcadores que el inglés, «CidIA» en lugar
//      de la marca) y hace que el idioma «es…» lo use; en lib/main.js, además, que la preferencia
//      de idioma «es» (la de CidIA) y los idiomas «es-…» de Windows lo elijan al arrancar;
//   2. quita del menú «Aplicación» «Buscar actualizaciones…» (CidIA se actualiza con su
//      instalador; la app no tiene app-update.yml) y «Gestionar la orden dsh…» (instalaría en el
//      PATH una orden dsh que choca con la de DeepSeek Harness si está instalada);
//   3. vuelve a escribir el app.asar: cabecera nueva con los tres ficheros al final (tamaño,
//      posición y sumas SHA-256 de integridad nuevas) y el resto de los datos tal cual;
//   4. comprueba el resultado: cada fichero del asar contra su suma de integridad, el diccionario
//      evaluado (vm) para «es», «es-ES», «en-US» y «zh-CN», y el menú sin esas dos entradas.
//
// Cada cambio se busca por un texto exacto que debe salir una sola vez: si la app base cambia, el
// script se para en lugar de parchear a ciegas. Solo acepta el app.asar original de la 0.2.0-rc.2
// (sha256 fijado). Electron no comprueba la integridad del asar al arrancar: el fusible
// EnableEmbeddedAsarIntegrityValidation está apagado (marca-app.ps1 lo comprueba y se para si no).
//
//   node app/instalador/traducir-app.mjs --asar <app\resources\app.asar> [--version-cidia 0.1.0]
//   node app/instalador/traducir-app.mjs --asar <...> --comprobar      (solo comprueba; código = fallos)
//
// verificar.mjs usa comprobarApp() sobre la instalación. Node 22, sin dependencias.
import { closeSync, fstatSync, openSync, readFileSync, readSync, renameSync, rmSync, writeSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import vm from 'node:vm'

const AQUI = dirname(fileURLToPath(import.meta.url))
/** sha256 del resources\app.asar de la 0.2.0-rc.2 tal como sale de su instalador oficial. */
export const ASAR_ORIGINAL_SHA256 = '983ca71114e6dfd353fc79af5a1f9481a250ee64c2a3c757673029b811b23bc2'
export const FICHEROS = ['lib/main.js', 'lib/preload-app.cjs', 'lib/preload-welcome.cjs']
const MARCA = '// CidIA: textos en castellano y menú sin actualizaciones ni orden dsh (app/instalador/traducir-app.mjs).\n'
const BLOQUE = 4 * 1024 * 1024
const NOMBRE = 'cidiaEs'

// ------------------------------------------------------------------ asar
function leerEn(fd, buf, posicion) {
  let hecho = 0
  while (hecho < buf.length) {
    const n = readSync(fd, buf, hecho, buf.length - hecho, posicion + hecho)
    if (n === 0) throw new Error('el app.asar termina antes de tiempo')
    hecho += n
  }
  return buf
}

/** Abre un app.asar: cabecera (JSON), dónde empiezan los datos y lectura de ficheros. */
export function abrirAsar(ruta) {
  const fd = openSync(ruta, 'r')
  try {
    const pre = leerEn(fd, Buffer.alloc(16), 0)
    if (pre.readUInt32LE(0) !== 4) throw new Error(`${ruta} no es un asar`)
    const tamCabecera = pre.readUInt32LE(4)
    const cabecera = JSON.parse(leerEn(fd, Buffer.alloc(pre.readUInt32LE(12)), 16).toString('utf8'))
    const base = 8 + tamCabecera
    return {
      fd, cabecera, base, tamano: fstatSync(fd).size,
      entrada(rutaInterna) {
        let n = cabecera
        for (const parte of rutaInterna.split('/')) { n = n?.files?.[parte]; if (!n) return null }
        return n
      },
      leer(e) { return leerEn(fd, Buffer.alloc(e.size), base + Number(e.offset)) },
      cerrar() { closeSync(fd) },
    }
  } catch (error) {
    closeSync(fd)
    throw error
  }
}

const sha256 = (b) => createHash('sha256').update(b).digest('hex')

function sha256Fichero(ruta) {
  const fd = openSync(ruta, 'r')
  try {
    const h = createHash('sha256')
    const trozo = Buffer.alloc(8 * 1024 * 1024)
    let pos = 0
    for (;;) {
      const n = readSync(fd, trozo, 0, trozo.length, pos)
      if (n === 0) break
      h.update(trozo.subarray(0, n))
      pos += n
    }
    return h.digest('hex')
  } finally {
    closeSync(fd)
  }
}

/** Suma de integridad de un fichero del asar, como la escribe @electron/asar. */
function integridad(buf) {
  const blocks = []
  for (let i = 0; i < buf.length; i += BLOQUE) blocks.push(sha256(buf.subarray(i, i + BLOQUE)))
  return { algorithm: 'SHA256', hash: sha256(buf), blockSize: BLOQUE, blocks }
}

function* ficherosDe(nodo, prefijo = '') {
  for (const [nombre, hijo] of Object.entries(nodo.files ?? {})) {
    const ruta = prefijo ? `${prefijo}/${nombre}` : nombre
    if (hijo.files) yield* ficherosDe(hijo, ruta)
    else yield [ruta, hijo]
  }
}

// ------------------------------------------------------------------ textos
export function leerTextos(ruta = join(AQUI, 'textos', 'app-es.json')) {
  const datos = JSON.parse(readFileSync(ruta, 'utf8'))
  if (!datos?.mensajes || typeof datos.mensajes !== 'object') throw new Error(`${ruta} no tiene «mensajes»`)
  return datos.mensajes
}

const ANCLA_IDIOMA = "/** Resolve Electron's locale to one shipped Desktop dictionary. */\n"
  + 'function resolveDesktopLocale(locale) {\n'
  + '\treturn locale.toLowerCase().startsWith("zh") ? {'
const FIN_IDIOMA = '\t\tmessages: en\n\t};\n}\n'

/** Cambios de cada fichero: [texto que debe salir una vez, sustituto, qué es]. */
function cambios(rutaInterna, mensajes) {
  const diccionario = `/** CidIA: castellano (app/instalador/textos/app-es.json). */\nconst ${NOMBRE} = ${JSON.stringify(mensajes, null, '\t')};\n`
  const lista = [[
    ANCLA_IDIOMA,
    diccionario + ANCLA_IDIOMA.replace('\treturn locale', `\tif (locale.toLowerCase().startsWith("es")) return {\n\t\tid: "es",\n\t\tmessages: ${NOMBRE}\n\t};\n\treturn locale`),
    'diccionario «es»',
  ]]
  if (rutaInterna === 'lib/main.js') {
    lista.push(
      ['\tif (selected === "zh" || selected === "en") return resolveDesktopLocale(selected);\n',
        '\tif (selected === "zh" || selected === "en" || selected === "es") return resolveDesktopLocale(selected);\n',
        'preferencia de idioma «es» al arrancar'],
      ['\t\tif (primary === "zh" || primary === "en") return resolveDesktopLocale(primary);\n',
        '\t\tif (primary === "zh" || primary === "en" || primary === "es") return resolveDesktopLocale(primary);\n',
        'idiomas «es-…» de Windows al arrancar'],
      ['\t\t{ type: "separator" },\n'
        + '\t\t{\n\t\t\tlabel: currentDesktopLocale().messages.checkUpdatesMenu,\n\t\t\tclick: () => {\n\t\t\t\topenUpdatePrompt(true);\n\t\t\t}\n\t\t},\n'
        + '\t\t...process.platform === "darwin" || process.platform === "win32" ? [{\n\t\t\tlabel: currentDesktopLocale().messages.cliCommandMenu,\n\t\t\tclick: () => {\n\t\t\t\tcommandManager.show();\n\t\t\t}\n\t\t}] : [],\n',
        '\t\t// CidIA: sin «Buscar actualizaciones…» (se actualiza con su instalador) ni «Gestionar la orden dsh…».\n',
        'menú «Aplicación» sin buscar actualizaciones ni la orden dsh'],
    )
  }
  return lista
}

/** Aplica los cambios a un fichero; cada ancla debe salir exactamente una vez. */
export function parchearTexto(rutaInterna, texto, mensajes) {
  if (texto.startsWith(MARCA)) throw new Error(`${rutaInterna} ya está traducido`)
  if (texto.includes(NOMBRE)) throw new Error(`${rutaInterna} ya usa el nombre ${NOMBRE}`)
  let salida = texto
  for (const [ancla, sustituto, que] of cambios(rutaInterna, mensajes)) {
    const veces = salida.split(ancla).length - 1
    if (veces !== 1) throw new Error(`la app base ha cambiado: ${que} (${rutaInterna}) aparece ${veces} veces y debía aparecer una`)
    salida = salida.replace(ancla, () => sustituto)
  }
  return MARCA + salida
}

/** Mensajes listos para la app: los de app-es.json con la versión de CidIA en «Acerca de». */
export function mensajesParaApp(versionCidia, ruta) {
  const m = { ...leerTextos(ruta) }
  for (const k of Object.keys(m)) m[k] = m[k].replaceAll('{cidia}', versionCidia)
  return m
}

// ------------------------------------------------------------------ comprobaciones
const marcadores = (s) => [...String(s).matchAll(/\{[^{}]+\}/g)].map(x => x[0]).sort().join(' ')

/** Evalúa los diccionarios y la elección de idioma de un fichero ya parcheado. */
function evaluarIdioma(rutaInterna, texto) {
  const desde = texto.indexOf('const en = {')
  const inicio = texto.indexOf('function resolveDesktopLocale(locale) {', desde)
  const fin = texto.indexOf(FIN_IDIOMA, inicio)
  if (desde < 0 || inicio < 0 || fin < 0) throw new Error(`no se encuentran los diccionarios en ${rutaInterna}`)
  let codigo = texto.slice(desde, fin + FIN_IDIOMA.length)
  if (rutaInterna === 'lib/main.js') {
    const a = texto.indexOf('function resolveDesktopStartupLocale(preference, languages) {')
    const b = texto.indexOf('/** Replace named placeholders', a)
    if (a < 0 || b < 0) throw new Error('no se encuentra resolveDesktopStartupLocale en lib/main.js')
    codigo += texto.slice(a, b)
  }
  const ctx = {}
  vm.runInNewContext(`${codigo}\nthis.en = en; this.zh = zh; this.es = typeof ${NOMBRE} === 'undefined' ? null : ${NOMBRE};`
    + ' this.idioma = resolveDesktopLocale;'
    + (rutaInterna === 'lib/main.js' ? ' this.alArrancar = resolveDesktopStartupLocale;' : ''), ctx, { timeout: 2000 })
  return ctx
}

/**
 * Comprueba un app.asar traducido. Devuelve [{ ok, texto, detalle }].
 * completa: también la integridad de todos los ficheros del asar (unos 120 MB).
 */
export function comprobarApp(rutaAsar, { completa = false } = {}) {
  const res = []
  const anotar = (ok, texto, detalle = '') => res.push({ ok: Boolean(ok), texto, detalle })
  let asar
  try {
    asar = abrirAsar(rutaAsar)
  } catch (error) {
    anotar(false, 'app.asar de la app', String(error.message ?? error))
    return res
  }
  try {
    for (const rutaInterna of FICHEROS) {
      const e = asar.entrada(rutaInterna)
      if (!e) { anotar(false, `${rutaInterna} en el app.asar`, 'no está'); continue }
      const buf = asar.leer(e)
      const integra = e.integrity?.hash === sha256(buf)
      const texto = buf.toString('utf8')
      if (!texto.startsWith(MARCA)) {
        anotar(false, `castellano en ${rutaInterna}`, integra ? 'sin traducir (app base sin el parche de CidIA)' : 'suma de integridad incorrecta')
        continue
      }
      let c
      try { c = evaluarIdioma(rutaInterna, texto) } catch (error) { anotar(false, `castellano en ${rutaInterna}`, error.message); continue }
      const problemas = []
      if (!integra) problemas.push('suma de integridad incorrecta')
      const es = c.es
      if (!es) problemas.push('sin diccionario es')
      else {
        const claves = Object.keys(c.en)
        const faltan = claves.filter(k => typeof es[k] !== 'string')
        const sobran = Object.keys(es).filter(k => !(k in c.en))
        if (faltan.length) problemas.push(`faltan ${faltan.join(', ')}`)
        if (sobran.length) problemas.push(`sobran ${sobran.join(', ')}`)
        for (const k of claves) {
          if (typeof es[k] !== 'string') continue
          if (marcadores(es[k]) !== marcadores(c.en[k])) problemas.push(`marcadores distintos en ${k}`)
          if (/DeepSeek|Feishu|\{cidia\}|\u2014/i.test(es[k])) problemas.push(`texto no permitido en ${k}`)
        }
        if (es.application !== 'Aplicación' || es.edit !== 'Edición') problemas.push('menú sin traducir')
      }
      const probar = (entrada, esperado) => {
        const r = c.idioma(entrada)
        if (r?.id !== esperado) problemas.push(`«${entrada}» da ${r?.id}`)
      }
      probar('es', 'es'); probar('es-ES', 'es'); probar('en-US', 'en'); probar('zh-CN', 'zh-CN')
      if (rutaInterna === 'lib/main.js') {
        const arranque = (pref, lenguas, esperado) => {
          const r = c.alArrancar(pref, lenguas)
          if (r?.id !== esperado) problemas.push(`al arrancar con ${pref} y ${lenguas.join(',')} da ${r?.id}`)
        }
        arranque('es', ['en-US'], 'es'); arranque(null, ['es-ES', 'en-US'], 'es'); arranque(null, ['fr-FR', 'en-US'], 'en'); arranque('en', ['es-ES'], 'en')
        const a = texto.indexOf('const applicationItems = () => [')
        const b = texto.indexOf('const devToolsItems', a)
        const menu = a >= 0 && b > a ? texto.slice(a, b) : ''
        if (!menu) problemas.push('no se encuentra el menú «Aplicación»')
        else if (/checkUpdatesMenu|cliCommandMenu/.test(menu)) problemas.push('el menú «Aplicación» aún busca actualizaciones o gestiona la orden dsh')
      }
      anotar(problemas.length === 0, `castellano en ${rutaInterna}`, problemas.length ? problemas.slice(0, 6).join('; ') : `${Object.keys(c.en).length} textos · menú «${es.application} · ${es.edit}»`)
    }
    if (completa) {
      let total = 0
      const malos = []
      for (const [ruta, e] of ficherosDe(asar.cabecera)) {
        if (e.unpacked || e.link || !e.integrity) continue
        total += 1
        if (sha256(asar.leer(e)) !== e.integrity.hash) malos.push(ruta)
      }
      const fin = Math.max(...[...ficherosDe(asar.cabecera)].filter(([, e]) => !e.unpacked && !e.link && e.size).map(([, e]) => Number(e.offset) + e.size))
      if (asar.base + fin !== asar.tamano) malos.push(`tamaño del fichero (${asar.tamano}, esperado ${asar.base + fin})`)
      anotar(malos.length === 0, 'integridad de todos los ficheros del app.asar', malos.length ? malos.slice(0, 5).join(', ') : `${total} ficheros`)
    }
  } finally {
    asar.cerrar()
  }
  return res
}

// ------------------------------------------------------------------ parche
/** Traduce el app.asar en su sitio (escribe <asar>.parcial y lo cambia al terminar). */
export function traducirApp(rutaAsar, versionCidia, { textos } = {}) {
  if (!/^\d+\.\d+\.\d+/.test(versionCidia ?? '')) throw new Error(`versión de CidIA no válida: ${versionCidia}`)
  const sha = sha256Fichero(rutaAsar)
  if (sha !== ASAR_ORIGINAL_SHA256) {
    throw new Error(`${rutaAsar} no es el app.asar original de la 0.2.0-rc.2 (sha256 ${sha}); vuelve a extraer la app`)
  }
  const mensajes = mensajesParaApp(versionCidia, textos)
  const asar = abrirAsar(rutaAsar)
  const parcial = rutaAsar + '.parcial'
  let fd = null
  try {
    // Los datos actuales terminan en el último byte del fichero: lo nuevo va detrás.
    const finDatos = asar.tamano - asar.base
    const nuevos = []
    let posicion = finDatos
    for (const rutaInterna of FICHEROS) {
      const e = asar.entrada(rutaInterna)
      if (!e || e.unpacked || e.link) throw new Error(`la app base ha cambiado: falta ${rutaInterna} en el app.asar`)
      const original = asar.leer(e)
      if (e.integrity?.hash !== sha256(original)) throw new Error(`${rutaInterna} no coincide con su suma de integridad`)
      const buf = Buffer.from(parchearTexto(rutaInterna, original.toString('utf8'), mensajes), 'utf8')
      e.size = buf.length
      e.offset = String(posicion)
      e.integrity = integridad(buf)
      posicion += buf.length
      nuevos.push(buf)
    }
    // Cabecera: Pickle con la longitud de la cadena JSON, la cadena y relleno hasta múltiplo de 4.
    const json = Buffer.from(JSON.stringify(asar.cabecera), 'utf8')
    const relleno = (4 - (json.length % 4)) % 4
    const carga = 4 + json.length + relleno
    const pre = Buffer.alloc(16)
    pre.writeUInt32LE(4, 0)
    pre.writeUInt32LE(4 + carga, 4)
    pre.writeUInt32LE(carga, 8)
    pre.writeUInt32LE(json.length, 12)
    rmSync(parcial, { force: true })
    fd = openSync(parcial, 'w')
    writeSync(fd, pre)
    writeSync(fd, json)
    if (relleno) writeSync(fd, Buffer.alloc(relleno))
    const trozo = Buffer.alloc(8 * 1024 * 1024)
    for (let pos = 0; pos < finDatos;) {
      const n = Math.min(trozo.length, finDatos - pos)
      leerEn(asar.fd, trozo.subarray(0, n), asar.base + pos)
      writeSync(fd, trozo, 0, n)
      pos += n
    }
    for (const buf of nuevos) writeSync(fd, buf)
    closeSync(fd)
    fd = null
  } catch (error) {
    if (fd !== null) closeSync(fd)
    rmSync(parcial, { force: true })
    throw error
  } finally {
    asar.cerrar()
  }
  const fallos = comprobarApp(parcial, { completa: true }).filter(r => !r.ok)
  if (fallos.length) {
    rmSync(parcial, { force: true })
    throw new Error('el app.asar traducido no pasa las comprobaciones: ' + fallos.map(f => `${f.texto} (${f.detalle})`).join('; '))
  }
  renameSync(parcial, rutaAsar)
  return sha256Fichero(rutaAsar)
}

// ------------------------------------------------------------------ línea de órdenes
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2)
  const opcion = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d }
  const rutaAsar = opcion('--asar', null)
  if (!rutaAsar) {
    console.error('Uso: node traducir-app.mjs --asar <app\\resources\\app.asar> [--version-cidia X.Y.Z] [--comprobar]')
    process.exit(2)
  }
  if (args.includes('--comprobar')) {
    const res = comprobarApp(rutaAsar, { completa: args.includes('--completa') })
    for (const r of res) console.log(`${r.ok ? 'OK' : 'FALLO'} ${r.texto}${r.detalle ? ' · ' + r.detalle : ''}`)
    process.exit(res.filter(r => !r.ok).length)
  }
  const version = opcion('--version-cidia', null)
    ?? JSON.parse(readFileSync(join(AQUI, '..', 'plugins', 'cidia', 'package.json'), 'utf8')).version
  try {
    const sha = traducirApp(rutaAsar, version)
    for (const r of comprobarApp(rutaAsar)) console.log(`${r.ok ? 'OK' : 'FALLO'} ${r.texto}${r.detalle ? ' · ' + r.detalle : ''}`)
    console.log(`App base en castellano (CidIA ${version}): app.asar ${sha}`)
  } catch (error) {
    console.error(`CidIA (castellano de la app): ${error.message}`)
    process.exit(1)
  }
}
