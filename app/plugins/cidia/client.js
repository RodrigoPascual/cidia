// Cliente del plugin CidIA (renderer de la app de escritorio, origen dsh-app://app).
//
// La interfaz de CidIA es la aplicación web que sirve el gateway. Este módulo la muestra dentro
// de la app como paneles de la barra lateral: cada panel (fila 'sidebar.panellist' + vista
// 'main' con la misma clave) pinta un <iframe> a 'cidia/gw/app/<ruta>?embed=1', que el Host
// del plugin reenvía al gateway. Mismo origen que la app: sin CORS y con localStorage común.
//
// Además:
//  · Puente de sesión: la interfaz guarda el token en localStorage 'cidia.token' y avisa con
//    postMessage({tipo:'cidia:sesion'}); este módulo se lo pasa al Host (/cidia/sesion), que
//    fija la credencial del modelo y reconecta el MCP. Sin sesión, el Host da un token de
//    invitado que se deja en localStorage para que el copiloto funcione sin iniciar sesión.
//  · Paneles según perfil.servicios (GET /api/auth/yo, validado por el Host).
//  · Marca CidIA (barra lateral, estado vacío del chat y título de la ventana).
//  · Idioma: registra 'es' y los diccionarios en castellano de la interfaz de la app.
//  · Micrófono: Electron solo concede el micrófono al marco principal; la interfaz embebida
//    puede pedir aquí que se grabe por ella (mensajes 'cidia:microfono').
window.__ModuleLoader__.load({
  id: 'cidia',
  factory(require) {
    const React = require('react')
    const P = require('@deepseek-ai/dsh-client-ui-primitives')
    const h = React.createElement
    const { useEffect, useRef, useState } = React

    const CLAVE_TOKEN = 'cidia.token'
    const RAIZ_APP = 'cidia/gw/app'
    const RUTA_APP_ABSOLUTA = '/cidia/gw/app'
    const AMARILLO = '#F2C200'
    const TINTA = '#1F2328'

    // ---------------------------------------------------------------- estilos
    // Un <style> creado durante el factory queda etiquetado (data-plugin) por el cargador y se
    // retira al desactivar el plugin. Solo tokens de tema de la app (--dsw-alias-*).
    const estilo = document.createElement('style')
    estilo.textContent = `
      .cidia-panel { height: 100%; display: flex; flex-direction: column; min-height: 0;
        background: var(--dsw-alias-bg-base, #fff); color: var(--dsw-alias-label-primary, #1f2328); }
      .cidia-panel-cabecera { flex: none; display: flex; align-items: center; gap: 10px;
        padding: max(10px, calc(var(--dsh-frame-top-clearance, 0px) - 26px)) 20px 10px;
        border-bottom: 1px solid var(--dsw-alias-border-l2, rgba(127,127,127,.18)); min-height: 44px; box-sizing: border-box; }
      .cidia-panel-cabecera h1 { margin: 0; font-size: 14px; font-weight: 600; letter-spacing: .01em; }
      .cidia-panel-cabecera .cidia-espacio { flex: 1; }
      .cidia-panel-cuerpo { position: relative; flex: 1; min-height: 0; }
      .cidia-marco { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; display: block;
        background: var(--dsw-alias-bg-base, #fff); }
      .cidia-velo { position: absolute; inset: 0; display: flex; flex-direction: column; gap: 14px; padding: 28px 32px;
        background: var(--dsw-alias-bg-base, #fff); transition: opacity .18s ease; }
      .cidia-velo.oculto { opacity: 0; pointer-events: none; }
      .cidia-hueso { border-radius: 10px; background: var(--dsw-alias-bg-layer-1, rgba(127,127,127,.12));
        animation: cidia-latido 1.4s ease-in-out infinite; }
      @keyframes cidia-latido { 0%, 100% { opacity: .55 } 50% { opacity: 1 } }
      .cidia-aviso { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; padding: 24px; }
      .cidia-aviso-caja { max-width: 440px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 10px; }
      .cidia-aviso-caja h2 { margin: 6px 0 0; font-size: 18px; font-weight: 600; }
      .cidia-aviso-caja p { margin: 0; font-size: 13px; line-height: 1.5; color: var(--dsw-alias-label-secondary, #5b6470); }
      .cidia-aviso-caja code { font-size: 12px; padding: 2px 6px; border-radius: 6px; background: var(--dsw-alias-bg-layer-1, rgba(127,127,127,.12)); }
      .cidia-sesion { display: flex; align-items: center; gap: 8px; width: 100%; min-width: 0; padding: 4px 6px; border: 0;
        border-radius: 10px; background: transparent; color: inherit; cursor: pointer; font: inherit; text-align: left; }
      .cidia-sesion:hover { background: var(--dsw-alias-bg-layer-1, rgba(127,127,127,.12)); }
      .cidia-sesion:focus-visible { outline: 2px solid ${AMARILLO}; outline-offset: 1px; }
      .cidia-avatar { flex: none; display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px;
        border-radius: 50%; background: ${AMARILLO}; color: ${TINTA}; font-size: 11px; font-weight: 700; position: relative; }
      .cidia-avatar.invitado { background: var(--dsw-alias-bg-layer-1, rgba(127,127,127,.18)); color: inherit; }
      .cidia-punto { position: absolute; right: -1px; bottom: -1px; width: 8px; height: 8px; border-radius: 50%;
        background: #2da44e; box-shadow: 0 0 0 2px var(--dsw-alias-bg-base, #fff); }
      .cidia-punto.mal { background: #cf222e; }
      .cidia-sesion-textos { min-width: 0; display: flex; flex-direction: column; line-height: 1.2; }
      .cidia-sesion-nombre { font-size: 13px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .cidia-sesion-rol { font-size: 11px; color: var(--dsw-alias-label-tertiary, #8a919a); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .cidia-ficha { display: flex; flex-direction: column; gap: 14px; }
      .cidia-ficha-cabeza { display: flex; align-items: center; gap: 12px; }
      .cidia-ficha-cabeza .cidia-avatar { width: 44px; height: 44px; font-size: 16px; }
      .cidia-ficha dl { margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 6px 14px; font-size: 13px; }
      .cidia-ficha dt { color: var(--dsw-alias-label-tertiary, #8a919a); }
      .cidia-ficha dd { margin: 0; }
      .cidia-botonera { display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; }
    `
    document.head.appendChild(estilo)

    // ---------------------------------------------------------------- marca
    /** Logo de CidIA: cuadrado amarillo redondeado con una C oscura y un punto (web/public/cidia.svg). */
    function MarcaCidia({ size = 24, className }) {
      return h('svg', { width: size, height: size, viewBox: '0 0 40 40', className, 'aria-hidden': 'true', focusable: 'false' },
        h('rect', { width: 40, height: 40, rx: 11, fill: AMARILLO }),
        h('path', { d: 'M27.4 13.6a9.2 9.2 0 1 0 0 12.8', fill: 'none', stroke: TINTA, strokeWidth: 4.4, strokeLinecap: 'round' }),
        h('circle', { cx: 29.2, cy: 20, r: 2.7, fill: TINTA }))
    }
    function NombreCidia() {
      return h('span', { style: { fontWeight: 650, letterSpacing: '.01em' } }, 'CidIA')
    }

    // ---------------------------------------------------------------- catálogo de paneles
    // servicio: el de perfil.servicios (GET /api/auth/yo) que da acceso al panel.
    const PANELES = [
      { id: 'cidia.acceso', titulo: 'Acceso', ruta: '/acceso', sinSesion: true, icono: 'IconUserOutlineRegular' },
      { id: 'cidia.inicio', titulo: 'Inicio', ruta: '/', servicio: 'perfil', icono: 'IconSparkleRegular' },
      { id: 'cidia.copiloto', titulo: 'Copiloto', ruta: '/copiloto', servicio: 'chat', sinSesion: true, icono: 'IconThinkOutlineRegular' },
      { id: 'cidia.planta', titulo: 'Modo planta', ruta: '/planta', servicio: 'planta', icono: 'IconPlayOutlineRegular' },
      { id: 'cidia.formacion', titulo: 'Formación', ruta: '/formacion', servicio: 'formacion', icono: 'IconSkillOutlineRegular' },
      { id: 'cidia.evaluacion', titulo: 'Evaluación', ruta: '/evaluacion', servicio: 'evaluacion', icono: 'IconChecklistOutlineRegular' },
      { id: 'cidia.progreso', titulo: 'Mi progreso', ruta: '/progreso', servicio: 'progreso', icono: 'IconGaugeOutlineRegular' },
      { id: 'cidia.aportaciones', titulo: 'Aportaciones', ruta: '/aportaciones', servicio: 'aportaciones', icono: 'IconEnhanceOutlineRegular' },
      { id: 'cidia.espacio', titulo: 'Espacio de trabajo', ruta: '/espacio', servicio: 'espacio', icono: 'IconFolderOpenOutlineRegular' },
      { id: 'cidia.captura', titulo: 'Captura', ruta: '/captura', servicio: 'captura', icono: 'IconMicrophoneOutlineRegular' },
      { id: 'cidia.instrucciones', titulo: 'Instrucciones', ruta: '/instrucciones', servicio: 'instrucciones', icono: 'IconListPenOutlineRegular' },
      { id: 'cidia.documentos', titulo: 'Documentos', ruta: '/documentos', servicio: 'documentos', icono: 'IconDeliverDocRegular' },
      { id: 'cidia.validar', titulo: 'Validar', ruta: '/validar', servicio: 'validar', icono: 'IconCheckCircleOutlineRegular' },
      { id: 'cidia.lagunas', titulo: 'Lagunas', ruta: '/lagunas', servicio: 'lagunas', icono: 'IconQuestionOutlineRegular' },
      { id: 'cidia.equipo', titulo: 'Equipo', ruta: '/equipo', servicio: 'equipo', icono: 'IconUsersOutlineRegular' },
      { id: 'cidia.admin', titulo: 'Administración', ruta: '/admin/organizacion', servicio: 'admin', icono: 'IconShieldOutlineRegular' },
      // Sin fila en la barra lateral: se abre desde el botón de sesión.
      { id: 'cidia.perfil', titulo: 'Mi perfil', ruta: '/perfil', servicio: 'perfil', oculto: true, icono: 'IconUserOutlineRegular' },
    ]
    const NOMBRE_ROL = { invitado: 'Sin sesión', empleado: 'Empleado', jefe: 'Jefe de equipo', admin: 'Administración' }

    /** Icono de las primitivas de la app; si una versión no lo trae, el destello genérico. */
    function icono(nombre) {
      return P[nombre] ?? P.IconSparkleRegular ?? (({ size }) => h(MarcaCidia, { size }))
    }

    /** ¿Debe verse el panel con este estado de sesión? */
    function panelVisible(panel, estado) {
      if (estado.modo !== 'usuario') return panel.sinSesion === true
      if (panel.id === 'cidia.acceso') return false
      return Array.isArray(estado.perfil?.servicios) && estado.perfil.servicios.includes(panel.servicio)
    }

    // ---------------------------------------------------------------- estado observable
    // El renderizador de la app convierte inject().hooks.cidia en la prop useCidia(selector).
    let estado = { fase: 'cargando', modo: 'sin_conexion', perfil: null, conectado: true, servidor: null, error: null, generacion: 0 }
    const oyentes = new Set()
    const almacen = {
      getSnapshot: () => estado,
      subscribe(oyente) { oyentes.add(oyente); return () => { oyentes.delete(oyente) } },
    }
    function cambiar(parcial) {
      estado = { ...estado, ...parcial }
      for (const oyente of [...oyentes]) oyente()
    }

    // ---------------------------------------------------------------- Host del plugin
    class ErrorCidia extends Error {
      constructor(estadoHttp, mensaje) { super(mensaje); this.estado = estadoHttp }
    }
    async function host(ruta, opciones = {}) {
      let r
      try {
        r = await fetch('cidia/' + ruta, {
          method: opciones.metodo ?? 'GET',
          headers: opciones.cuerpo !== undefined ? { 'content-type': 'application/json' } : undefined,
          body: opciones.cuerpo !== undefined ? JSON.stringify(opciones.cuerpo) : undefined,
          cache: 'no-store',
        })
      } catch {
        throw new ErrorCidia(0, 'No hay conexión con la app.')
      }
      let datos = null
      try { datos = await r.json() } catch { datos = null }
      if (!r.ok) throw new ErrorCidia(r.status, datos?.detail ?? `Error ${r.status}`)
      return datos
    }

    // ---------------------------------------------------------------- token de la interfaz
    function leerToken() {
      try { return window.localStorage.getItem(CLAVE_TOKEN) } catch { return null }
    }
    function guardarToken(token) {
      try {
        if (token) window.localStorage.setItem(CLAVE_TOKEN, token)
        else window.localStorage.removeItem(CLAVE_TOKEN)
      } catch { /* almacenamiento no disponible */ }
    }

    /** Token que la interfaz web tiene ahora (el último que este módulo ha visto o dejado). */
    let tokenInterfaz = leerToken()
    let ultimoUsuario = null
    // Siembras de token de invitado recientes: evita bucles si el servidor rechaza los tokens.
    const siembras = []
    // Operaciones de sesión en serie (eventos de varias pestañas, sondeo y botones).
    let cola = Promise.resolve()
    const enCola = (op) => { const r = cola.then(op, op); cola = r.catch(() => undefined); return r }
    let alCambiarModo = () => {}

    /** Aplica lo que responde el Host y decide si hay que recargar los paneles. */
    function aplicarHost(s, { recargar = false } = {}) {
      const modo = s?.modo ?? 'sin_conexion'
      const usuario = modo === 'usuario' ? (s.perfil?.id ?? s.perfil?.usuario ?? 'usuario') : null
      // Sin sesión de usuario, la interfaz usa el token de invitado del Host.
      if (modo !== 'usuario' && s?.token && s.token !== tokenInterfaz) {
        const ahora = Date.now()
        while (siembras.length && ahora - siembras[0] > 60_000) siembras.shift()
        if (siembras.length < 4) {
          siembras.push(ahora)
          tokenInterfaz = s.token
          guardarToken(s.token)
          recargar = true
        }
      }
      const modoAnterior = estado.modo
      if (usuario !== ultimoUsuario) { recargar = true; ultimoUsuario = usuario }
      cambiar({
        fase: 'listo',
        modo,
        perfil: s?.perfil ?? null,
        conectado: s?.conectado !== false,
        servidor: s?.servidor ?? estado.servidor,
        error: s?.error ?? null,
        generacion: recargar ? estado.generacion + 1 : estado.generacion,
      })
      if (modoAnterior !== modo) alCambiarModo(modoAnterior, modo)
    }

    /** Panel de CidIA que se ve ahora (o null si se ve el chat u otra sección de la app). */
    function panelEnPantalla() {
      try { return document.querySelector('[data-cidia-panel]')?.getAttribute('data-cidia-panel') ?? null } catch { return null }
    }

    function sinConexion(error) {
      cambiar({ fase: 'listo', conectado: false, error: error?.message ?? String(error) })
    }

    /** La interfaz ha cambiado de token (inicio o cierre de sesión, caducidad, invitado nuevo). */
    function alTokenDeInterfaz(nuevo) {
      nuevo = typeof nuevo === 'string' && nuevo !== '' ? nuevo : null
      if (nuevo === tokenInterfaz) return
      tokenInterfaz = nuevo
      void enCola(async () => {
        try {
          const s = await host('sesion', { metodo: 'POST', cuerpo: { token: nuevo } })
          aplicarHost(s)
          // «Continuar sin sesión» desde Acceso: la persona quiere el copiloto.
          if (nuevo && s?.modo === 'invitado' && panelEnPantalla() === 'cidia.acceso') abrirPanel('cidia.copiloto')
        } catch (error) {
          if (error.estado === 401) {
            // Token caducado: fuera, y el Host vuelve a invitado.
            tokenInterfaz = null
            guardarToken(null)
            try { aplicarHost(await host('sesion', { metodo: 'POST', cuerpo: { token: null } }), { recargar: true }) } catch (e) { sinConexion(e) }
          } else {
            sinConexion(error)
          }
        }
      })
    }

    /** Arranque y reintentos: adopta el token guardado o se queda con el de invitado del Host. */
    function sincronizar() {
      return enCola(async () => {
        const guardado = leerToken()
        tokenInterfaz = guardado
        try {
          if (guardado) {
            try {
              aplicarHost(await host('sesion', { metodo: 'POST', cuerpo: { token: guardado } }))
              return
            } catch (error) {
              if (error.estado !== 401) throw error
              tokenInterfaz = null
              guardarToken(null)
            }
          }
          aplicarHost(await host('sesion'))
        } catch (error) {
          sinConexion(error)
        }
      })
    }

    /** Cierre de sesión pedido desde la app (botón de la barra lateral). */
    function cerrarSesion() {
      return enCola(async () => {
        try {
          const s = await host('sesion', { metodo: 'DELETE' })
          tokenInterfaz = null
          guardarToken(null)
          aplicarHost(s, { recargar: true })
        } catch (error) {
          sinConexion(error)
        }
      })
    }

    // ---------------------------------------------------------------- mensajes de la interfaz
    const grabaciones = new Map()

    /** Graba audio en el marco principal para la interfaz embebida (el iframe no puede). */
    async function microfono(evento) {
      const d = evento.data
      const fuente = evento.source
      const responder = (mensaje) => {
        try { fuente?.postMessage({ tipo: 'cidia:microfono', id: d.id, ...mensaje }, evento.origin) } catch { /* marco cerrado */ }
      }
      if (d.accion === 'empezar') {
        if (grabaciones.has(d.id)) return
        try {
          const flujo = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
          const tipo = window.MediaRecorder?.isTypeSupported?.('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : ''
          const grabador = new MediaRecorder(flujo, tipo ? { mimeType: tipo } : undefined)
          const g = { grabador, flujo, trozos: [], inicio: Date.now(), cancelada: false, limite: null }
          // Si la sección se cierra sin parar, el micrófono no se queda abierto: 10 min como mucho.
          g.limite = setTimeout(() => { if (grabador.state !== 'inactive') grabador.stop() }, 10 * 60_000)
          grabador.ondataavailable = (e) => { if (e.data && e.data.size) g.trozos.push(e.data) }
          grabador.onstop = () => {
            clearTimeout(g.limite)
            flujo.getTracks().forEach(t => t.stop())
            grabaciones.delete(d.id)
            if (g.cancelada) { responder({ estado: 'cancelada' }); return }
            const audio = new Blob(g.trozos, { type: grabador.mimeType || 'audio/webm' })
            responder({ estado: 'lista', audio, duracion_ms: Date.now() - g.inicio })
          }
          grabaciones.set(d.id, g)
          grabador.start()
          responder({ estado: 'grabando' })
        } catch {
          responder({ estado: 'error', mensaje: 'No se puede usar el micrófono. Revisa los permisos de Windows.' })
        }
      } else if (d.accion === 'parar' || d.accion === 'cancelar') {
        const g = grabaciones.get(d.id)
        if (!g) { responder({ estado: 'error', mensaje: 'No hay ninguna grabación en curso.' }); return }
        g.cancelada = d.accion === 'cancelar'
        if (g.grabador.state !== 'inactive') g.grabador.stop()
      }
    }

    function alMensaje(evento) {
      // Solo marcos de la propia app (la interfaz embebida tiene el mismo origen).
      if (evento.origin !== window.location.origin) return
      const d = evento.data
      if (!d || typeof d !== 'object') return
      if (d.tipo === 'cidia:sesion') alTokenDeInterfaz(d.token)
      else if (d.tipo === 'cidia:microfono' && typeof d.id === 'string') void microfono(evento)
    }
    function alAlmacenamiento(evento) {
      if (evento.key === CLAVE_TOKEN || evento.key === null) alTokenDeInterfaz(leerToken())
    }

    // ---------------------------------------------------------------- vistas
    /** Última ruta interna de cada panel, para volver donde se estaba. */
    const ultimaRuta = new Map()

    function srcDe(ruta) {
      return RAIZ_APP + ruta + (ruta.includes('?') ? '&' : '?') + 'embed=1'
    }

    function Esqueleto() {
      return h(React.Fragment, null,
        h('div', { className: 'cidia-hueso', style: { width: '38%', height: 26 } }),
        h('div', { className: 'cidia-hueso', style: { width: '62%', height: 14 } }),
        h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 14, marginTop: 10 } },
          [0, 1, 2].map(i => h('div', { key: i, className: 'cidia-hueso', style: { height: 120 } }))),
        h('div', { className: 'cidia-hueso', style: { width: '100%', height: 180 } }))
    }

    function AvisoSinConexion({ servidor, mensaje, onReintentar, ocupado }) {
      const Icono = icono('IconWarningTriangleOutlineRegular')
      return h('div', { className: 'cidia-aviso', role: 'alert' },
        h('div', { className: 'cidia-aviso-caja' },
          h(Icono, { size: 28 }),
          h('h2', null, 'No hay conexión con el servidor CidIA'),
          h('p', null, mensaje ?? 'Comprueba que el equipo está en la red de la empresa y que el servidor está encendido.'),
          servidor ? h('p', null, 'Servidor: ', h('code', null, servidor)) : null,
          h(P.Button, { variant: 'primary', size: 'md', onClick: onReintentar, disabled: ocupado },
            ocupado ? 'Conectando…' : 'Reintentar')))
    }

    /** Guarda la ruta interna de un panel justo antes de que su iframe desaparezca. */
    function recordarRuta(panel, nodo, generacion) {
      try {
        const lugar = nodo?.contentWindow?.location
        if (!lugar || !lugar.pathname.startsWith(RUTA_APP_ABSOLUTA)) return
        const interna = lugar.pathname.slice(RUTA_APP_ABSOLUTA.length) || '/'
        // Solo rutas de la propia sección: si desde Inicio se ha ido a otra, se vuelve a Inicio.
        const propia = panel.ruta === '/' ? interna === '/' : interna === panel.ruta || interna.startsWith(panel.ruta + '/')
        if (!propia) { ultimaRuta.delete(panel.id); return }
        const params = new URLSearchParams(lugar.search)
        params.delete('embed')
        const q = params.toString()
        ultimaRuta.set(panel.id, { generacion, ruta: interna + (q ? '?' + q : '') })
      } catch { /* marco ya descargado */ }
    }

    /** Fábrica de la vista principal de un panel: cabecera arrastrable + interfaz web embebida. */
    function crearPanel(panel) {
      const Icono = icono(panel.icono)
      function PanelCidia({ useCidia }) {
        const fase = useCidia(s => s.fase)
        const generacion = useCidia(s => s.generacion)
        const conectado = useCidia(s => s.conectado)
        const servidor = useCidia(s => s.servidor)
        const marco = useRef(null)
        const [cargando, setCargando] = useState(true)
        const [fallo, setFallo] = useState(null)
        const [reintentando, setReintentando] = useState(false)
        const [intento, setIntento] = useState(0)

        // La ruta guardada solo vale dentro de la misma sesión.
        const recordada = ultimaRuta.get(panel.id)
        const ruta = recordada && recordada.generacion === generacion ? recordada.ruta : panel.ruta
        const src = srcDe(ruta)

        // Ref de función: React la llama con null mientras el iframe sigue en el documento,
        // que es el momento de leer dónde estaba la persona.
        const refMarco = React.useCallback((nodo) => {
          if (nodo) { marco.current = nodo; return }
          recordarRuta(panel, marco.current, generacion)
          marco.current = null
        }, [generacion])

        useEffect(() => { setCargando(true); setFallo(null) }, [generacion, intento])
        useEffect(() => {
          if (!cargando || fallo) return undefined
          const espera = setTimeout(() => setFallo('La página tarda demasiado en responder.'), 30_000)
          return () => clearTimeout(espera)
        }, [cargando, fallo, generacion, intento])

        function alCargar() {
          // Si el servidor no responde, el Host devuelve un JSON de error en lugar de la página.
          try {
            const doc = marco.current?.contentDocument
            if (doc && doc.contentType && doc.contentType !== 'text/html') {
              let detalle = null
              try { detalle = JSON.parse(doc.body?.innerText ?? '')?.detail } catch { /* no es JSON */ }
              setFallo(detalle ?? 'El servidor CidIA no ha devuelto la interfaz.')
              setCargando(false)
              return
            }
          } catch { /* sin acceso al documento */ }
          setFallo(null)
          setCargando(false)
        }

        async function reintentar() {
          setReintentando(true)
          await sincronizar()
          setReintentando(false)
          setIntento(n => n + 1)
        }

        let cuerpo
        if (fase !== 'listo') {
          cuerpo = h('div', { className: 'cidia-velo' }, h(Esqueleto))
        } else if (!conectado || fallo) {
          cuerpo = h(AvisoSinConexion, { servidor, mensaje: fallo ?? undefined, onReintentar: reintentar, ocupado: reintentando })
        } else {
          cuerpo = h(React.Fragment, null,
            h('iframe', {
              key: `${generacion}-${intento}`,
              ref: refMarco,
              className: 'cidia-marco',
              src,
              title: `CidIA · ${panel.titulo}`,
              allow: 'microphone; camera; clipboard-read; clipboard-write; fullscreen; autoplay',
              onLoad: alCargar,
            }),
            h('div', { className: `cidia-velo ${cargando ? '' : 'oculto'}`, 'aria-hidden': 'true' }, h(Esqueleto)))
        }

        return h('div', { className: 'cidia-panel', 'data-cidia-panel': panel.id },
          h('header', { className: 'cidia-panel-cabecera', 'data-window-drag': '' },
            h(Icono, { size: 16 }),
            h('h1', null, panel.titulo),
            h('span', { className: 'cidia-espacio' }),
            fase === 'listo' ? h(P.Button, {
              variant: 'ghost', size: 'sm', icon: h(icono('IconRefreshOutlineRegular'), { size: 14 }),
              title: 'Recargar esta sección', 'aria-label': 'Recargar esta sección',
              style: { WebkitAppRegion: 'no-drag' }, onClick: () => setIntento(n => n + 1),
            }) : null),
          h('div', { className: 'cidia-panel-cuerpo' }, cuerpo))
      }
      PanelCidia.displayName = `CidiaPanel(${panel.id})`
      return PanelCidia
    }

    function iniciales(nombre) {
      const partes = String(nombre ?? '').split(/\s+/).filter(Boolean)
      return (partes.slice(0, 2).map(p => p[0]).join('') || '?').toUpperCase()
    }

    let abrirPanel = () => {}

    /** Botón de sesión al pie de la barra lateral, junto a Ajustes (owner: { wide }). */
    function AccionSesion({ wide, useCidia }) {
      const modo = useCidia(s => s.modo)
      const perfil = useCidia(s => s.perfil)
      const conectado = useCidia(s => s.conectado)
      const [abierto, setAbierto] = useState(false)
      const [saliendo, setSaliendo] = useState(false)
      const usuario = modo === 'usuario' && perfil
      const nombre = usuario ? perfil.nombre : 'Iniciar sesión'
      const detalle = usuario ? (NOMBRE_ROL[perfil.rol] ?? perfil.rol) : (conectado ? 'Servicios básicos' : 'Sin conexión')
      const titulo = usuario ? `${perfil.nombre} · ${detalle}` : 'Iniciar sesión en CidIA'

      const boton = h('button', {
        type: 'button', className: 'cidia-sesion', title: titulo, 'aria-label': titulo,
        onClick: () => { if (usuario) setAbierto(true); else abrirPanel('cidia.acceso') },
      },
      h('span', { className: `cidia-avatar ${usuario ? '' : 'invitado'}` },
        usuario ? (perfil.iniciales ?? iniciales(perfil.nombre)) : h(icono('IconUserOutlineRegular'), { size: 14 }),
        h('span', { className: `cidia-punto ${conectado ? '' : 'mal'}` })),
      wide ? h('span', { className: 'cidia-sesion-textos' },
        h('span', { className: 'cidia-sesion-nombre' }, nombre),
        h('span', { className: 'cidia-sesion-rol' }, detalle)) : null)

      if (!usuario) return boton
      const filas = [
        ['Usuario', perfil.usuario],
        ['Puesto', perfil.puesto],
        ['Departamento', perfil.departamento?.nombre],
        ['Formación activa', (perfil.formaciones ?? []).map(f => f.puesto ? `${f.departamento} · ${f.puesto}` : f.departamento).join(', ')],
      ].filter(([, v]) => v)
      return h(React.Fragment, null, boton,
        h(P.Modal, {
          open: abierto, onClose: () => setAbierto(false), title: 'Tu sesión en CidIA', closeLabel: 'Cerrar',
          footer: h('div', { className: 'cidia-botonera' },
            h(P.Button, { variant: 'outline', onClick: () => { setAbierto(false); abrirPanel('cidia.perfil') } }, 'Ver mi perfil'),
            h(P.Button, {
              variant: 'primary', disabled: saliendo,
              onClick: async () => { setSaliendo(true); await cerrarSesion(); setSaliendo(false); setAbierto(false) },
            }, saliendo ? 'Cerrando sesión…' : 'Cerrar sesión')),
        },
        h('div', { className: 'cidia-ficha' },
          h('div', { className: 'cidia-ficha-cabeza' },
            h('span', { className: 'cidia-avatar' }, perfil.iniciales ?? iniciales(perfil.nombre)),
            h('div', null,
              h('div', { style: { fontWeight: 600, fontSize: 15 } }, perfil.nombre),
              h('div', { className: 'cidia-sesion-rol', style: { fontSize: 12 } }, detalle))),
          filas.length ? h('dl', null, ...filas.flatMap(([k, v]) => [h('dt', { key: k + 't' }, k), h('dd', { key: k + 'd' }, v)])) : null)))
    }

    // ---------------------------------------------------------------- idioma
    async function cargarDiccionarios() {
      try {
        const r = await fetch('cidia/idioma/es.json', { cache: 'no-store' })
        return r.ok ? await r.json() : {}
      } catch {
        return {}
      }
    }

    // ---------------------------------------------------------------- título de la ventana
    // La app pone «<sesión>, raya larga, DeepSeek Harness»; aquí queda «<sesión> · CidIA».
    function marcarTitulo() {
      const t = document.title ?? ''
      if (t.includes('DeepSeek Harness')) document.title = t.replace(/ \u2014 DeepSeek Harness/g, ' · CidIA').replace(/DeepSeek Harness/g, 'CidIA')
      else if (t.trim() === '') document.title = 'CidIA'
    }

    return {
      inject: ['slots'],
      apply(ctx) {
        let activo = true
        const ganchos = () => ({ hooks: { cidia: almacen } })

        // Navegación entre paneles (servicio de la app, opcional).
        let disposicion = null
        ctx.inject(['layout'], (c) => {
          disposicion = c.layout
          return () => { disposicion = null }
        })
        abrirPanel = (id) => { try { disposicion?.selectPanel(id) } catch { /* panel aún no registrado */ } }

        // Marca: ocupa los slots 'single' con prioridad menor que la oficial (0).
        ctx.slots.inject('sidebar.brand.mark', () => ctx.slots.register({ name: 'sidebar.brand.mark', priority: -10 }, MarcaCidia))
        ctx.slots.inject('sidebar.brand.name', () => ctx.slots.register({ name: 'sidebar.brand.name', priority: -10 }, NombreCidia))
        ctx.slots.inject('conversation.hero.brand.mark', () =>
          ctx.slots.register({ name: 'conversation.hero.brand.mark', priority: -10 }, MarcaCidia))
        ctx.slots.inject('sidebar.footer.action', () => ctx.slots.register({
          name: 'sidebar.footer.action', id: 'cidia.sesion', order: -10, inject: ganchos,
        }, AccionSesion))

        // Paneles según la sesión: se registran y retiran en vivo. 'main' y 'sidebar.panellist'
        // los declaran plugins distintos; se espera a ambos y la fila va después de la vista.
        const vistas = new Map(PANELES.map(p => [p.id, crearPanel(p)]))
        const iconos = new Map(PANELES.map((p) => {
          const Icono = icono(p.icono)
          const Fila = ({ size }) => h(Icono, { size })
          Fila.displayName = `CidiaIcono(${p.id})`
          return [p.id, Fila]
        }))
        ctx.slots.inject('main', () => ctx.slots.inject('sidebar.panellist', () => {
          const activos = new Map()
          const sincronizarPaneles = () => {
            PANELES.forEach((panel, i) => {
              const ver = panelVisible(panel, estado)
              if (ver && !activos.has(panel.id)) {
                const quitarVista = ctx.slots.register({ name: 'main', key: panel.id, inject: ganchos }, vistas.get(panel.id))
                const quitarFila = panel.oculto ? () => {} : ctx.slots.register({
                  name: 'sidebar.panellist', id: panel.id, order: 100 + i, label: panel.titulo,
                }, iconos.get(panel.id))
                activos.set(panel.id, () => { quitarFila(); quitarVista() })
              } else if (!ver && activos.has(panel.id)) {
                activos.get(panel.id)()
                activos.delete(panel.id)
              }
            })
          }
          sincronizarPaneles()
          const dejar = almacen.subscribe(sincronizarPaneles)
          return () => { dejar(); for (const quitar of activos.values()) quitar(); activos.clear() }
        }))

        // Al entrar o salir se lleva a la persona a la pantalla que corresponde.
        let primera = true
        alCambiarModo = (antes, ahora) => {
          if (ahora === 'usuario' && antes !== 'usuario') abrirPanel('cidia.inicio')
          else if (antes === 'usuario' && ahora !== 'usuario') abrirPanel('cidia.acceso')
        }
        const quitarPrimera = almacen.subscribe(() => {
          if (!primera || estado.fase !== 'listo') return
          primera = false
          // Al abrir la app: Inicio con sesión; si no, Acceso.
          setTimeout(() => abrirPanel(estado.modo === 'usuario' ? 'cidia.inicio' : 'cidia.acceso'), 0)
        })

        // Idioma: castellano para la interfaz de la app (lo que falte cae en inglés).
        ctx.inject(['locale'], (c) => {
          try {
            c.effect(() => c.locale.addLanguage({ id: 'es', label: 'Español', fallback: 'en' }), 'cidia: idioma es')
          } catch (error) {
            console.warn('cidia: no se pudo registrar el castellano', error)
          }
          let vigente = true
          void cargarDiccionarios().then((diccionarios) => {
            if (!vigente) return
            for (const [ns, dic] of Object.entries(diccionarios)) {
              if (ns.startsWith('_') || !dic || typeof dic !== 'object') continue
              try { c.effect(() => c.locale.register(ns, 'es', dic), `cidia: es ${ns}`) } catch { /* espacio no disponible */ }
            }
          })
          return () => { vigente = false }
        })

        // Título de la ventana: «CidIA» en lugar de la marca de la app base.
        const raizTitulo = document.querySelector?.('head') ?? null
        let observador = null
        if (typeof MutationObserver === 'function' && raizTitulo) {
          observador = new MutationObserver(marcarTitulo)
          observador.observe(raizTitulo, { childList: true, characterData: true, subtree: true })
        }
        marcarTitulo()

        // Puente con la interfaz web y sondeo suave del Host (caducidades, servidor caído):
        // cada minuto con conexión y cada 15 s sin ella.
        window.addEventListener('message', alMensaje)
        window.addEventListener('storage', alAlmacenamiento)
        let sondeo = null
        const programarSondeo = () => {
          sondeo = setTimeout(() => {
            void enCola(async () => {
              try { aplicarHost(await host('sesion')) } catch (error) { sinConexion(error) }
            }).finally(() => { if (activo) programarSondeo() })
          }, estado.conectado ? 60_000 : 15_000)
        }
        void sincronizar().finally(() => { if (activo) programarSondeo() })

        ctx.effect(() => () => {
          activo = false
          if (sondeo !== null) clearTimeout(sondeo)
          quitarPrimera()
          observador?.disconnect()
          window.removeEventListener('message', alMensaje)
          window.removeEventListener('storage', alAlmacenamiento)
          for (const g of grabaciones.values()) { g.cancelada = true; try { g.grabador.stop() } catch { /* ya parada */ } }
          alCambiarModo = () => {}
          abrirPanel = () => {}
          if (/^CidIA$| · CidIA$/.test(document.title)) {
            document.title = document.title.replace(/( · )?CidIA$/, m => (m.startsWith(' ') ? ' \u2014 ' : '') + 'DeepSeek Harness')
          }
        }, 'cidia: puente de sesión, título y micrófono')
      },
    }
  },
})
