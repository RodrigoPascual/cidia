// Pruebas del puente de micrófono del cliente del plugin (client.js, mensajes 'cidia:microfono'):
// la interfaz embebida pide grabar y el marco principal graba por ella. Sin React ni navegador:
// getUserMedia, MediaRecorder y AudioContext simulados, y el marco de la interfaz como un objeto
// con postMessage y closed.
//
//   cd app/plugins/cidia && node --test "pruebas/*.test.*"   (Node 22 no acepta una carpeta)

const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const esperar = (ms = 20) => new Promise(r => setTimeout(r, ms))

function montar() {
  // ---- dispositivos simulados
  const micro = { pendientes: [], fallar: false, pistasParadas: 0, contextosCerrados: 0, grabadores: [] }
  const navigator = {
    mediaDevices: {
      getUserMedia(restricciones) {
        assert.deepEqual(Object.keys(restricciones), ['audio'], 'solo audio')
        return new Promise((ok, mal) => micro.pendientes.push(() => {
          if (micro.fallar) { mal(new Error('NotAllowedError')); return }
          ok({ getTracks: () => [{ stop: () => { micro.pistasParadas += 1 } }] })
        }))
      },
    },
  }
  micro.abrir = () => micro.pendientes.shift()()
  class MediaRecorder {
    static isTypeSupported() { return true }
    constructor(flujo, opciones) { this.flujo = flujo; this.mimeType = opciones?.mimeType ?? ''; this.state = 'inactive'; micro.grabadores.push(this) }
    start() { this.state = 'recording' }
    stop() {
      if (this.state === 'inactive') throw new Error('InvalidStateError')
      this.state = 'inactive'
      setTimeout(() => { this.ondataavailable?.({ data: new Blob(['voz-de-prueba'], { type: this.mimeType }) }); this.onstop?.() }, 5)
    }
  }
  class AudioContext {
    createAnalyser() { return { fftSize: 0, getByteTimeDomainData: (m) => { for (let i = 0; i < m.length; i++) m[i] = i % 2 ? 160 : 96 } } }
    createMediaStreamSource() { return { connect() {} } }
    resume() { return Promise.resolve() }
    close() { micro.contextosCerrados += 1; return Promise.resolve() }
  }

  // ---- navegador y app simulados (lo justo para cargar el cliente)
  const oyentes = { message: new Set(), storage: new Set() }
  const almacen = new Map()
  const window = {
    location: { origin: 'dsh-app://app' },
    localStorage: { getItem: k => almacen.get(k) ?? null, setItem: (k, v) => almacen.set(k, String(v)), removeItem: k => almacen.delete(k) },
    addEventListener: (tipo, f) => oyentes[tipo]?.add(f),
    removeEventListener: (tipo, f) => oyentes[tipo]?.delete(f),
    MediaRecorder,
    AudioContext,
    __ModuleLoader__: { load: (r) => { registro = r } },
  }
  let registro = null
  const document = { title: 'CidIA', createElement: () => ({}), head: { appendChild() {} }, querySelector: () => null }
  const fetch = async (url) => ({
    ok: true, status: 200,
    json: async () => (url === 'cidia/sesion' ? { modo: 'invitado', token: 'inv-1', perfil: { invitado: true, servicios: ['chat'] }, conectado: true } : {}),
  })
  const contexto = {
    window, document, navigator, fetch, MediaRecorder, Blob, Uint8Array, Promise, console, URLSearchParams,
    setTimeout, clearTimeout, setInterval, clearInterval,
  }
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', 'client.js'), 'utf8'), contexto)
  const nada = () => null
  const React = { createElement: nada, Fragment: 'f', useEffect() {}, useRef() { return { current: null } }, useState: v => [v, () => {}], useCallback: f => f }
  const primitivas = new Proxy({}, { get: () => nada })
  const plugin = registro.factory(spec => ({ react: React, '@deepseek-ai/dsh-client-ui-primitives': primitivas })[spec])
  const efectos = []
  plugin.apply({
    slots: { inject() { return () => {} }, register() { return () => {} } },
    effect(fn) { const d = fn(); efectos.push(d); return d },
    inject() {},
  })
  const descargar = () => { for (const d of efectos.splice(0)) if (typeof d === 'function') d() }

  /** Marco de la interfaz: guarda lo que le responde el plugin. */
  function marco() {
    return { closed: false, recibidos: [], postMessage(m, origen) { assert.equal(origen, 'dsh-app://app'); this.recibidos.push(m) } }
  }
  const pedir = (fuente, id, accion, origin = 'dsh-app://app') => {
    for (const f of oyentes.message) f({ origin, source: fuente, data: { tipo: 'cidia:microfono', id, accion } })
  }
  const estados = (fuente, sinNivel = true) => fuente.recibidos.map(m => m.estado).filter(e => !sinNivel || e !== 'nivel')
  return { micro, oyentes, marco, pedir, estados, descargar }
}

test('micrófono: graba por la interfaz, manda el nivel y entrega el audio', async () => {
  const { micro, marco, pedir, estados, descargar } = montar()
  try {
    const f = marco()
    pedir(f, 'g1', 'empezar')
    await esperar()
    assert.deepEqual(estados(f), [], 'nada hasta que se abre el micrófono')
    micro.abrir()
    await esperar()
    assert.deepEqual(estados(f), ['grabando'])
    await esperar(260)
    const niveles = f.recibidos.filter(m => m.estado === 'nivel')
    assert.ok(niveles.length >= 2, 'manda el nivel unas 10 veces por segundo')
    assert.ok(niveles.every(m => m.id === 'g1' && m.nivel >= 0 && m.nivel <= 1))
    assert.ok(niveles[0].nivel > 0.5, 'el nivel sigue a la señal')
    pedir(f, 'g1', 'parar')
    await esperar(40)
    const lista = f.recibidos.find(m => m.estado === 'lista')
    assert.ok(lista, 'llega el audio')
    assert.equal(lista.id, 'g1')
    assert.equal(lista.audio.type, 'audio/webm;codecs=opus')
    assert.equal(await lista.audio.text(), 'voz-de-prueba')
    assert.ok(lista.duracion_ms >= 250)
    assert.equal(micro.pistasParadas, 1, 'micrófono cerrado')
    assert.equal(micro.contextosCerrados, 1, 'medidor cerrado')
    const antes = f.recibidos.length
    await esperar(150)
    assert.equal(f.recibidos.length, antes, 'sin niveles después de parar')
  } finally {
    descargar()
  }
})

test('micrófono: si sueltan antes de que se abra, se cancela al momento y se cierra al abrirse', async () => {
  const { micro, marco, pedir, estados, descargar } = montar()
  try {
    const f = marco()
    pedir(f, 'g2', 'empezar')
    await esperar()
    pedir(f, 'g2', 'parar')
    await esperar()
    assert.deepEqual(estados(f), ['cancelada'], 'respuesta inmediata, sin el error de «no hay ninguna grabación»')
    micro.abrir()
    await esperar(150)
    assert.equal(micro.grabadores.length, 0, 'no se llega a grabar')
    assert.equal(micro.pistasParadas, 1, 'el micrófono se cierra en cuanto se abre')
    // Las interfaces anteriores esperan a 'empezar' un 'grabando' o un 'error': reciben una pista útil.
    assert.deepEqual(estados(f), ['cancelada', 'error'])
    assert.match(f.recibidos.at(-1).mensaje, /Mantén pulsado/)
    pedir(f, 'g2', 'parar')
    await esperar()
    assert.equal(f.recibidos.at(-1).mensaje, 'No hay ninguna grabación en curso.')
  } finally {
    descargar()
  }
})

test('micrófono: cancelar, marco cerrado, permisos denegados, otro origen y descarga del plugin', async () => {
  const { micro, marco, pedir, estados, descargar } = montar()
  try {
    // Cancelar durante la grabación: sin audio.
    const a = marco()
    pedir(a, 'c1', 'empezar')
    await esperar()
    micro.abrir()
    await esperar()
    pedir(a, 'c1', 'cancelar')
    await esperar(40)
    assert.deepEqual(estados(a), ['grabando', 'cancelada'])
    assert.equal(micro.pistasParadas, 1)

    // El marco desaparece (otra sección): la grabación se cancela sola.
    const b = marco()
    pedir(b, 'c2', 'empezar')
    await esperar()
    micro.abrir()
    await esperar()
    b.closed = true
    await esperar(160)
    assert.equal(micro.grabadores.at(-1).state, 'inactive')
    assert.equal(micro.pistasParadas, 2)

    // Permisos de Windows denegados.
    const c = marco()
    micro.fallar = true
    pedir(c, 'c3', 'empezar')
    await esperar()
    micro.abrir()
    await esperar()
    assert.deepEqual(estados(c), ['error'])
    assert.match(c.recibidos[0].mensaje, /permisos de Windows/)
    micro.fallar = false

    // Mensajes de otro origen: ni caso.
    const d = marco()
    pedir(d, 'c4', 'empezar', 'http://malicioso')
    await esperar()
    assert.equal(micro.pendientes.length, 0)
    assert.deepEqual(d.recibidos, [])

    // Al descargar el plugin no queda ningún micrófono abierto.
    const e = marco()
    pedir(e, 'c5', 'empezar')
    await esperar()
    micro.abrir()
    await esperar()
    descargar()
    await esperar(40)
    assert.equal(micro.grabadores.at(-1).state, 'inactive')
    assert.equal(micro.pistasParadas, 3)
  } finally {
    descargar()
  }
})
