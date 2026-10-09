// Pruebas del cliente del plugin (client.js): simula window.__ModuleLoader__, la tabla de módulos
// de la app (React 18.3.1 real y primitivas con la firma de la 0.2.0-rc.2), ctx.slots, el
// servicio de disposición (selectPanel), el de idioma, localStorage, postMessage y el Host
// (/cidia/sesion). Renderiza las vistas con react-dom/server.
//
// React se toma de servidor/web/node_modules (o de CIDIA_REACT_DIR).
//
//   node --test app/plugins/cidia/pruebas/

const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const DIR_REACT = process.env.CIDIA_REACT_DIR
  ?? path.join(__dirname, '..', '..', '..', '..', 'servidor', 'web', 'node_modules')
const hayReact = fs.existsSync(path.join(DIR_REACT, 'react', 'package.json'))

test('cliente: paneles por sesión, puente con la interfaz, marca, idioma y título', { skip: !hayReact && 'sin React 18 en ' + DIR_REACT }, async () => {
  const React = require(path.join(DIR_REACT, 'react'))
  const { renderToStaticMarkup } = require(path.join(DIR_REACT, 'react-dom', 'server'))
  const h = React.createElement

  // Primitivas simuladas (misma firma que ui-primitives 0.2.0-rc.2).
  const icono = nombre => ({ size }) => h('i', { 'data-icono': nombre, 'data-size': size })
  const primitivas = new Proxy({
    Button: ({ variant, size, icon, children, ...resto }) => h('button', { type: 'button', 'data-variant': variant, ...resto }, icon, children),
    Modal: ({ open, title, children, footer }) => (open ? h('dialog', { 'aria-label': title }, children, footer) : null),
  }, { get: (t, k) => (k in t ? t[k] : (typeof k === 'string' && k.startsWith('Icon') ? icono(k) : undefined)) })
  const tabla = { react: React, '@deepseek-ai/dsh-client-ui-primitives': primitivas }

  // ---- navegador simulado
  const estilos = []
  const almacen = new Map()
  const oyentes = { message: new Set(), storage: new Set() }
  const document = {
    title: 'DeepSeek Harness',
    createElement: tag => ({ tag, textContent: '' }),
    head: { appendChild: el => estilos.push(el) },
    querySelector: () => null,
  }
  const localStorage = {
    getItem: k => (almacen.has(k) ? almacen.get(k) : null),
    setItem: (k, v) => { almacen.set(k, String(v)) },
    removeItem: (k) => { almacen.delete(k) },
  }
  const window = {
    location: { origin: 'dsh-app://app' },
    localStorage,
    addEventListener: (tipo, f) => oyentes[tipo]?.add(f),
    removeEventListener: (tipo, f) => oyentes[tipo]?.delete(f),
    __ModuleLoader__: { load: (r) => { registro = r } },
  }
  let registro = null

  // ---- Host simulado (/cidia/sesion y /cidia/idioma)
  const host = { modo: 'invitado', token: 'inv-1', perfil: { invitado: true, servicios: ['chat'] }, conectado: true }
  const perfilAna = {
    invitado: false, id: 7, usuario: 'ana', nombre: 'Ana Martín', iniciales: 'AM', rol: 'jefe', puesto: 'Montaje',
    servicios: ['chat', 'perfil', 'planta', 'formacion', 'evaluacion', 'progreso', 'validar', 'equipo'],
  }
  const llamadas = []
  async function fetch(url, init = {}) {
    const metodo = init.method ?? 'GET'
    llamadas.push([metodo, url, init.body ?? null])
    const r = (status, cuerpo) => ({ ok: status < 400, status, json: async () => cuerpo })
    if (url === 'cidia/idioma/es.json') return r(200, { _nota: 'x', common: { cancel: 'Cancelar' }, sidebar: { 'session.new': 'Nueva conversación' } })
    if (url !== 'cidia/sesion') return r(404, { detail: 'No existe.' })
    if (metodo === 'GET') {
      return r(200, { modo: host.modo, token: host.modo === 'invitado' ? host.token : null, perfil: host.perfil, conectado: host.conectado, servidor: 'http://srv:18700' })
    }
    if (metodo === 'DELETE') {
      Object.assign(host, { modo: 'invitado', token: 'inv-2', perfil: { invitado: true, servicios: ['chat'] } })
      return r(200, { modo: 'invitado', token: 'inv-2', perfil: host.perfil, conectado: true })
    }
    const { token } = JSON.parse(init.body)
    if (token === 'usr-ana-12345') {
      Object.assign(host, { modo: 'usuario', token, perfil: perfilAna })
      return r(200, { modo: 'usuario', token: null, perfil: perfilAna, conectado: true })
    }
    if (token === null) {
      Object.assign(host, { modo: 'invitado', token: 'inv-3', perfil: { invitado: true, servicios: ['chat'] } })
      return r(200, { modo: 'invitado', token: 'inv-3', perfil: host.perfil, conectado: true })
    }
    if (token.startsWith('inv-')) return r(200, { modo: 'invitado', token, perfil: host.perfil, conectado: host.conectado, servidor: 'http://srv:18700' })
    return r(401, { detail: 'La sesión ha caducado. Vuelve a iniciar sesión.' })
  }

  const contexto = { window, document, fetch, setTimeout, clearTimeout, console, URLSearchParams, Promise, Blob }
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', 'client.js'), 'utf8'), contexto)
  assert.equal(registro.id, 'cidia', 'el id del bundle es el nombre del paquete')
  const plugin = registro.factory((spec) => {
    if (!(spec in tabla)) throw new Error('módulo no disponible: ' + spec)
    return tabla[spec]
  })
  assert.deepEqual([...plugin.inject], ['slots'])
  assert.equal(estilos.length, 1, 'un <style> propio')

  // ---- ctx simulado
  const entradas = new Map() // `${name}|${key ?? id ?? ''}` -> { opciones, componente }
  const seleccionados = []
  const idioma = { lenguas: [], diccionarios: [] }
  const efectos = []
  const ctx = {
    slots: {
      inject(_clave, cb) { const e = cb(); return typeof e === 'function' ? e : () => {} },
      register(opciones, componente) {
        const k = `${opciones.name}|${opciones.key ?? opciones.id ?? ''}`
        assert.ok(!entradas.has(k), 'registro duplicado ' + k)
        entradas.set(k, { opciones, componente })
        return () => { entradas.delete(k) }
      },
    },
    effect(fn) { const d = fn(); efectos.push(d); return d },
    inject(servicios, cb) {
      const c = { effect: f => { const d = f(); efectos.push(d); return d } }
      if (servicios.includes('layout')) c.layout = { selectPanel: (id) => { if (id !== null && !entradas.has(`main|${id}`)) throw new Error('sin panel ' + id); seleccionados.push(id) } }
      if (servicios.includes('locale')) {
        c.locale = {
          addLanguage: (def) => { idioma.lenguas.push(def); return () => {} },
          register: (ns, lengua, dic) => { idioma.diccionarios.push([ns, lengua, Object.keys(dic).length]); return () => {} },
        }
      }
      const d = cb(c)
      if (typeof d === 'function') efectos.push(d)
    },
  }
  const claves = () => [...entradas.keys()].sort()
  const filas = () => claves().filter(k => k.startsWith('sidebar.panellist|')).map(k => k.split('|')[1])
  const esperar = (ms = 30) => new Promise(r => setTimeout(r, ms))
  // Los objetos creados dentro del contexto vm tienen otros prototipos: se comparan en JSON.
  const plano = x => JSON.parse(JSON.stringify(x))
  const descargar = () => { for (const d of efectos.splice(0)) if (typeof d === 'function') d() }

  plugin.apply(ctx)
  try {
  await esperar()

  // Marca con prioridad sobre la oficial y título de la ventana.
  assert.equal(entradas.get('sidebar.brand.mark|').opciones.priority, -10)
  assert.equal(entradas.get('sidebar.brand.name|').opciones.priority, -10)
  assert.equal(entradas.get('conversation.hero.brand.mark|').opciones.priority, -10)
  assert.match(renderToStaticMarkup(h(entradas.get('sidebar.brand.mark|').componente, { size: 24 })), /#F2C200/)
  assert.match(renderToStaticMarkup(h(entradas.get('sidebar.brand.name|').componente, {})), />CidIA</)
  assert.equal(document.title, 'CidIA')

  // Sin sesión: token de invitado sembrado para la interfaz, Acceso y Copiloto, y se abre Acceso.
  assert.equal(almacen.get('cidia.token'), 'inv-1')
  assert.deepEqual(filas(), ['cidia.acceso', 'cidia.copiloto'])
  assert.deepEqual(seleccionados, ['cidia.acceso'])

  // Idioma: castellano con respaldo en inglés y los diccionarios servidos por el Host.
  assert.deepEqual(plano(idioma.lenguas), [{ id: 'es', label: 'Español', fallback: 'en' }])
  assert.deepEqual(idioma.diccionarios, [['common', 'es', 1], ['sidebar', 'es', 1]])

  // Props que inyecta el renderizador: inject().hooks.cidia -> useCidia(selector).
  const props = (k, extra = {}) => {
    const { opciones } = entradas.get(k)
    const inyectado = opciones.inject ? opciones.inject() : {}
    const salida = { ...extra }
    for (const [nombre, fuente] of Object.entries(inyectado.hooks ?? {})) {
      salida['use' + nombre[0].toUpperCase() + nombre.slice(1)] = sel => sel(React.useSyncExternalStore(fuente.subscribe, fuente.getSnapshot, fuente.getSnapshot))
    }
    return salida
  }
  const pintar = (k, extra) => renderToStaticMarkup(h(entradas.get(k).componente, props(k, extra)))

  const copiloto = pintar('main|cidia.copiloto')
  assert.match(copiloto, /<iframe[^>]+src="cidia\/gw\/app\/copiloto\?embed=1"/)
  assert.match(copiloto, /title="CidIA · Copiloto"/)
  assert.match(copiloto, /data-window-drag/)
  assert.match(pintar('main|cidia.acceso'), /src="cidia\/gw\/app\/acceso\?embed=1"/)
  assert.match(pintar('sidebar.footer.action|cidia.sesion', { wide: true }), /Iniciar sesión/)
  assert.match(pintar('sidebar.panellist|cidia.copiloto', { size: 16, active: false }), /data-icono="IconThinkOutlineRegular"/)
  assert.equal(entradas.get('sidebar.panellist|cidia.copiloto').opciones.label, 'Copiloto')

  // Mensajes de otro origen se ignoran.
  const enviar = (datos, origin = 'dsh-app://app') => { for (const f of oyentes.message) f({ origin, data: datos, source: null }) }
  enviar({ tipo: 'cidia:sesion', token: 'usr-ana-12345' }, 'http://malicioso')
  await esperar()
  assert.equal(host.modo, 'invitado')

  // La interfaz inicia sesión: se avisa al Host y aparecen los paneles de sus servicios.
  almacen.set('cidia.token', 'usr-ana-12345')
  enviar({ tipo: 'cidia:sesion', token: 'usr-ana-12345', perfil: perfilAna })
  for (const f of oyentes.storage) f({ key: 'cidia.token', newValue: 'usr-ana-12345' }) // mismo cambio por storage
  await esperar()
  assert.equal(llamadas.filter(([m, u, b]) => m === 'POST' && u === 'cidia/sesion' && b?.includes('usr-ana')).length, 1, 'el mismo token se adopta una sola vez')
  assert.deepEqual(filas(), [
    'cidia.copiloto', 'cidia.equipo', 'cidia.evaluacion', 'cidia.formacion', 'cidia.inicio', 'cidia.planta', 'cidia.progreso', 'cidia.validar',
  ])
  assert.ok(entradas.has('main|cidia.perfil'), 'Mi perfil existe como vista sin fila')
  assert.ok(!entradas.has('sidebar.panellist|cidia.perfil'))
  assert.ok(!entradas.has('main|cidia.admin'), 'sin servicio admin no hay Administración')
  assert.ok(!entradas.has('main|cidia.acceso'))
  assert.equal(seleccionados.at(-1), 'cidia.inicio')
  assert.equal(entradas.get('sidebar.panellist|cidia.formacion').opciones.order < entradas.get('sidebar.panellist|cidia.validar').opciones.order, true)
  const pie = pintar('sidebar.footer.action|cidia.sesion', { wide: true })
  assert.match(pie, /Ana Martín/)
  assert.match(pie, /Jefe de equipo/)
  assert.match(pintar('main|cidia.inicio'), /src="cidia\/gw\/app\/\?embed=1"/)

  // La sesión caduca en la interfaz (borra el token): vuelve el invitado y se abre Acceso.
  almacen.delete('cidia.token')
  for (const f of oyentes.storage) f({ key: 'cidia.token', newValue: null })
  await esperar()
  assert.equal(almacen.get('cidia.token'), 'inv-3')
  assert.deepEqual(filas(), ['cidia.acceso', 'cidia.copiloto'])
  assert.equal(seleccionados.at(-1), 'cidia.acceso')

  // Un token que el servidor rechaza no deja la app en un estado raro.
  enviar({ tipo: 'cidia:sesion', token: 'token-caducado-123' })
  await esperar()
  assert.deepEqual(filas(), ['cidia.acceso', 'cidia.copiloto'])

  // «Continuar sin sesión» desde Acceso: el token de invitado nuevo se adopta y se abre Copiloto.
  document.querySelector = sel => (sel === '[data-cidia-panel]' ? { getAttribute: () => 'cidia.acceso' } : null)
  enviar({ tipo: 'cidia:sesion', token: 'inv-7', perfil: { invitado: true, servicios: ['chat'] } })
  await esperar()
  document.querySelector = () => null
  assert.ok(llamadas.some(([m, u, b]) => m === 'POST' && u === 'cidia/sesion' && b?.includes('inv-7')))
  assert.equal(seleccionados.at(-1), 'cidia.copiloto')

  // Sin servidor: la vista muestra un aviso útil en lugar de la interfaz.
  host.conectado = false
  enviar({ tipo: 'cidia:sesion', token: 'inv-9' })
  await esperar()
  const caido = pintar('main|cidia.copiloto')
  assert.match(caido, /No hay conexión con el servidor CidIA/)
  assert.match(caido, /http:\/\/srv:18700/)
  assert.match(caido, /Reintentar/)

  // Al descargar el plugin se retiran los oyentes y se devuelve el título.
  descargar()
  assert.equal(oyentes.message.size, 0)
  assert.equal(oyentes.storage.size, 0)
  assert.equal(document.title, 'DeepSeek Harness')
  } finally {
    descargar() // sin temporizadores colgando aunque falle una comprobación
  }
})
