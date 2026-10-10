// Grabador de escenas de CidIA: Edge (o Chrome) sin cabeza controlado por CDP que ejecuta una escena
// descrita en JSON y la graba como vídeo fluido de 1920x1080 a 30 fps.
//
//   node herramientas/video/grabador.mjs <escena.json | proyecto.json> --salida <carpeta>
//        [--solo id1,id2] [--base http://127.0.0.1:18700] [--secretos cidia.env]
//        [--voces <carpeta>] [--conectar 9333 [--objetivo /app/]] [--calidad 92] [--bitrate 20M]
//        [--conservar-fotogramas] [--sin-video] [--sin-sincronizar-voz]
//
// Con --voces y la narración ya sintetizada (voz.py narrar), en cada {"marca"} espera en directo a que
// termine la voz anterior, con las mismas reglas que montaje.py: el vídeo sale ya al ritmo de la voz.
//
// Cómo graba: Page.startScreencast entrega un fotograma JPEG cada vez que la página se repinta, con
// su marca de tiempo. Se guardan todos y después ffmpeg los une con su duración real (demuxer concat)
// y los pasa a 30 fps constantes: los ratos quietos repiten el último fotograma y las animaciones
// salen con su ritmo real. El cursor es un elemento inyectado en la página que sigue a los eventos de
// puntero reales que manda el grabador (Input.dispatchMouseEvent), así que también se ven los estados
// :hover de la interfaz.
//
// Escena (JSON):
//   { "id": "01-inicio-javier", "usuario": "javier", "ruta": "/app/", "escala": 1,
//     "microfono": "{voces}/microfono/llave.wav",          (opcional: lo que «oye» el micrófono)
//     "acciones": [ ... ], "duracion_minima_ms": 8000 }
// Acciones (cada una admite "pausa": ms después, por defecto 350 en las interactivas):
//   {"ir": "/app/ruta"}  navegación de la SPA (sin recargar); con "recargar": true, Page.navigate
//   {"clic": "selector"}  {"clicTexto": "texto visible", "dentro": "selector"}  ("doble": true)
//   {"hover": "selector"} / {"hoverTexto": "texto"}   lleva el cursor sin pulsar
//   {"escribir": ["selector", "texto"], "limpiar": true, "ms_tecla": 55}  tecleo carácter a carácter
//   {"tecla": "Enter"}  (también "Control+a", "Escape", "Tab", "ArrowDown"...)
//   {"seleccionar": ["selector de <select>", "valor o texto de la opción"]}
//   {"subir": "ruta del fichero", "clic": "selector" | "clicTexto": "texto"}  (selector de fichero)
//   {"esperar": ms}
//   {"esperarTexto": "texto", "max": 30000, "acelerar": true | "rótulo"}  (también "esperarSinTexto",
//       "esperarSelector"): la espera queda marcada y el montaje puede acelerarla avisándolo
//   {"mantenerMicro": ["selector", ms | "auto"]}  mantener pulsado para hablar (pointerdown ... pointerup);
//       "auto" = lo que dura el WAV del micrófono y un poco más
//   {"scroll": 400 | -400 | "selector", "en": "selector"}  rueda suave o scrollIntoView suave
//   {"resaltar": "selector" | "resaltarTexto": "texto", "ms": 1800, "nota": "texto opcional"}
//   {"cursor": false | true}   {"marca": "nombre"}  (marca de tiempo para sincronizar la voz)
//   {"eval": "expresión JS"}
// Marcadores {repo}, {voces}, {salida} y {escena} en rutas: raíz del repositorio, carpeta de voces
// (--voces), carpeta de salida y carpeta del fichero de la escena.
//
// Salida en --salida: <id>.mp4 y <id>.json (duración, marcas y esperas en ms desde el primer
// fotograma, errores de consola, excepciones y peticiones fallidas). Código de salida 1 si alguna
// acción falla o la página da errores: así se detectan antes del montaje.

import { spawn, spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { dirname, isAbsolute, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const AQUI = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(AQUI, '..', '..')

const args = process.argv.slice(2)
const opt = (n, d) => { const i = args.indexOf('--' + n); return i >= 0 ? args[i + 1] : d }
const flag = (n) => args.includes('--' + n)
const CON_VALOR = new Set(['salida', 'solo', 'base', 'secretos', 'voces', 'conectar', 'objetivo', 'calidad', 'bitrate', 'navegador'])
const entrada = args.find((a, i) => !a.startsWith('--') && !(i > 0 && CON_VALOR.has(args[i - 1].slice(2))))
if (!entrada) { console.error('Uso: node grabador.mjs <escena.json | proyecto.json> --salida <carpeta>'); process.exit(2) }

const BASE = (opt('base', process.env.CIDIA_BASE ?? 'http://127.0.0.1:18700')).replace(/\/$/, '')
const SALIDA = resolve(opt('salida', join(process.cwd(), 'grabaciones')))
const VOCES = resolve(opt('voces', join(SALIDA, '..', 'voces')))
const SECRETOS = opt('secretos', process.env.CIDIA_SECRETOS)
const CONECTAR = opt('conectar')
const CALIDAD = Number(opt('calidad', 92))
const BITRATE = opt('bitrate', '20M')
const SOLO = opt('solo')?.split(',').map((s) => s.trim()).filter(Boolean)
mkdirSync(SALIDA, { recursive: true })

const NAVEGADORES = [
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/usr/bin/chromium', '/usr/bin/google-chrome',
]

function buscarFfmpeg() {
  if (process.env.CIDIA_FFMPEG) return process.env.CIDIA_FFMPEG
  const h = join(REPO, 'servidor', 'gateway', '.herramientas')
  if (existsSync(h)) {
    for (const d of readdirSync(h).filter((x) => x.startsWith('ffmpeg-')).sort().reverse()) {
      const p = join(h, d, 'bin', process.platform === 'win32' ? 'ffmpeg.exe' : 'ffmpeg')
      if (existsSync(p)) return p
    }
  }
  return 'ffmpeg'
}
const FFMPEG = buscarFfmpeg()

const dormir = (ms) => new Promise((r) => setTimeout(r, ms))
const basenameNavegador = (p) => p.split(/[\\/]/).pop()
const puertoLibre = () => new Promise((ok) => { const s = createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => ok(p)) }) })
const ocultar = (t) => String(t).replace(/token=[^&\s"']+/g, 'token=***').replace(/Bearer\s+[\w.-]+/g, 'Bearer ***')

// ---------- Sesión: token por la API, sin imprimir contraseñas ni tokens ----------
let secretos = null
function leerSecretos() {
  if (secretos) return secretos
  if (!SECRETOS || !existsSync(SECRETOS)) throw new Error('Falta --secretos (fichero con CIDIA_DEMO_CONTRASENA y CIDIA_ADMIN_CONTRASENA) o CIDIA_SECRETOS')
  secretos = Object.fromEntries(readFileSync(SECRETOS, 'utf8').split(/\r?\n/).filter((l) => l.includes('=') && !l.trim().startsWith('#'))
    .map((l) => { const i = l.indexOf('='); return [l.slice(0, i).trim(), l.slice(i + 1).trim().replace(/^["']|["']$/g, '')] }))
  return secretos
}
const tokens = {}
function contrasenaDe(usuario) {
  if (!usuario) throw new Error('{contrasena} necesita "cuenta_acceso" en la escena')
  const s = leerSecretos()
  const c = usuario === 'admin' ? s.CIDIA_ADMIN_CONTRASENA : s.CIDIA_DEMO_CONTRASENA
  if (!c) throw new Error('Falta la contraseña en el fichero de secretos')
  return c
}
async function tokenDe(usuario) {
  if (tokens[usuario]) return tokens[usuario]
  const s = leerSecretos()
  const contrasena = usuario === 'admin' ? s.CIDIA_ADMIN_CONTRASENA : s.CIDIA_DEMO_CONTRASENA
  const r = await fetch(BASE + '/api/auth/login', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ usuario, contrasena }) })
  if (!r.ok) throw new Error(`No se puede iniciar sesión como ${usuario} (HTTP ${r.status})`)
  tokens[usuario] = (await r.json()).token
  return tokens[usuario]
}

// ---------- Script inyectado: cursor, onda de clic, halo de «mantener pulsado» y resaltado ----------
const SCRIPT_PAGINA = String.raw`(() => {
  // Solo en el documento principal: dentro de un iframe (los paneles de la app de escritorio) no se
  // dibuja otro cursor; el del documento principal lo mueve el grabador.
  if (window.__cc || window.top !== window) return;
  const cc = window.__cc = { x: -200, y: -200, visible: true };
  const css = ` + '`' + String.raw`
    #__cc { position: fixed; inset: 0; pointer-events: none; z-index: 2147483647; overflow: hidden; }
    #__cc .cc-cur { position: absolute; left: 0; top: 0; width: 34px; height: 34px; will-change: transform; }
    #__cc .cc-cur svg { width: 34px; height: 34px; display: block; transform-origin: 5px 3px;
      filter: drop-shadow(0 2px 3px rgba(0,0,0,.35)); transition: transform 110ms ease; }
    #__cc .cc-cur.pulsado svg { transform: scale(.84); }
    #__cc .cc-cur.oculto { opacity: 0; }
    #__cc .cc-onda { position: absolute; width: 18px; height: 18px; margin: -9px 0 0 -9px; border-radius: 50%;
      border: 3px solid #F2C200; background: rgba(242,194,0,.28); animation: ccOnda 560ms cubic-bezier(.2,.7,.3,1) forwards; }
    @keyframes ccOnda { from { transform: scale(.4); opacity: 1; } to { transform: scale(3.6); opacity: 0; } }
    #__cc .cc-halo { position: absolute; width: 64px; height: 64px; margin: -32px 0 0 -32px; border-radius: 50%;
      background: rgba(242,194,0,.25); border: 3px solid rgba(242,194,0,.95); animation: ccLatido 1s ease-in-out infinite; }
    @keyframes ccLatido { 0%,100% { transform: scale(.82); opacity: .95; } 50% { transform: scale(1.18); opacity: .55; } }
    #__cc .cc-marco { position: absolute; border-radius: 12px; opacity: 0;
      box-shadow: 0 0 0 4px #F2C200, 0 0 26px 8px rgba(242,194,0,.55);
      transition: opacity 320ms ease; }
    #__cc .cc-velo { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; transition: opacity 320ms ease; }
    #__cc .cc-marco.visible, #__cc .cc-velo.visible { opacity: 1; }
    #__cc .cc-nota { position: absolute; max-width: 520px; background: #1F2328; color: #fff; padding: 10px 16px;
      border-radius: 10px; border-left: 5px solid #F2C200; font: 600 19px/1.35 'Fira Sans', system-ui, sans-serif;
      box-shadow: 0 10px 30px rgba(0,0,0,.28); opacity: 0; transform: translateY(6px); transition: opacity 300ms ease, transform 300ms ease; }
    #__cc .cc-nota.visible { opacity: 1; transform: none; }
  ` + '`' + String.raw`;
  const svg = '<svg viewBox="0 0 34 34" xmlns="http://www.w3.org/2000/svg"><path d="M5 3 L5 27 L11.2 21.2 L15.4 30.6 L19.6 28.8 L15.5 19.6 L24 19.6 Z" fill="#1F2328" stroke="#ffffff" stroke-width="2" stroke-linejoin="round"/></svg>';
  let raiz, cur, marco, nota, halo, velo;
  const NS = 'http://www.w3.org/2000/svg';
  function montar() {
    if (!document.documentElement) return setTimeout(montar, 10);
    if (document.getElementById('__cc')) return;
    raiz = document.createElement('div'); raiz.id = '__cc';
    const st = document.createElement('style'); st.textContent = css; raiz.appendChild(st);
    // Velo que oscurece todo menos la zona resaltada (máscara SVG con un hueco redondeado).
    velo = document.createElementNS(NS, 'svg'); velo.setAttribute('class', 'cc-velo');
    velo.innerHTML = '<defs><mask id="__ccMascara"><rect width="100%" height="100%" fill="#fff"/><rect class="hueco" rx="12" fill="#000"/></mask></defs>'
      + '<rect width="100%" height="100%" fill="rgba(18,21,25,0.36)" mask="url(#__ccMascara)"/>';
    raiz.appendChild(velo);
    marco = document.createElement('div'); marco.className = 'cc-marco'; raiz.appendChild(marco);
    nota = document.createElement('div'); nota.className = 'cc-nota'; raiz.appendChild(nota);
    cur = document.createElement('div'); cur.className = 'cc-cur' + (cc.visible ? '' : ' oculto'); cur.innerHTML = svg; raiz.appendChild(cur);
    document.documentElement.appendChild(raiz);
    pintar();
  }
  function pintar() { if (cur) cur.style.transform = 'translate(' + (cc.x - 5) + 'px,' + (cc.y - 3) + 'px)'; if (halo) { halo.style.left = cc.x + 'px'; halo.style.top = cc.y + 'px'; } }
  cc.mover = (x, y) => { cc.x = x; cc.y = y; if (!document.getElementById('__cc')) montar(); pintar(); };
  cc.mostrar = (v) => { cc.visible = v; if (cur) cur.classList.toggle('oculto', !v); };
  cc.onda = (x, y) => { if (!raiz) return; const o = document.createElement('div'); o.className = 'cc-onda'; o.style.left = x + 'px'; o.style.top = y + 'px'; raiz.appendChild(o); setTimeout(() => o.remove(), 700); };
  cc.halo = (v) => { if (!raiz) return; if (v && !halo) { halo = document.createElement('div'); halo.className = 'cc-halo'; raiz.insertBefore(halo, cur); pintar(); } if (!v && halo) { halo.remove(); halo = null; } };
  cc.resaltar = (r, textoNota) => {
    if (!marco) return;
    if (!r) { marco.classList.remove('visible'); velo.classList.remove('visible'); nota.classList.remove('visible'); return; }
    const m = 8;
    Object.assign(marco.style, { left: (r.x - m) + 'px', top: (r.y - m) + 'px', width: (r.w + 2 * m) + 'px', height: (r.h + 2 * m) + 'px' });
    const h = velo.querySelector('.hueco');
    h.setAttribute('x', r.x - m); h.setAttribute('y', r.y - m); h.setAttribute('width', r.w + 2 * m); h.setAttribute('height', r.h + 2 * m);
    marco.classList.add('visible');
    if (cc.oscurecer !== false) velo.classList.add('visible');
    if (textoNota) {
      nota.textContent = textoNota;
      const abajo = r.y + r.h + m + 14, vh = innerHeight;
      nota.style.left = Math.max(16, Math.min(innerWidth - 540, r.x - m)) + 'px';
      nota.style.top = (abajo + 60 < vh ? abajo : Math.max(16, r.y - m - 64)) + 'px';
      nota.classList.add('visible');
    } else nota.classList.remove('visible');
  };
  const pos = (e) => cc.mover(e.clientX, e.clientY);
  addEventListener('pointermove', pos, true);
  addEventListener('pointerdown', (e) => { pos(e); if (cur) cur.classList.add('pulsado'); cc.onda(e.clientX, e.clientY); }, true);
  addEventListener('pointerup', () => { if (cur) cur.classList.remove('pulsado'); }, true);
  addEventListener('pointercancel', () => { if (cur) cur.classList.remove('pulsado'); }, true);
  // Localiza un elemento por selector o por texto visible y lo deja centrado si está fuera de la vista.
  const visible = (e) => { const r = e.getBoundingClientRect(); if (r.width < 1 || r.height < 1) return false; const s = (e.ownerDocument.defaultView || window).getComputedStyle(e); return s.visibility !== 'hidden' && s.display !== 'none' && Number(s.opacity) > 0.05; };
  const norm = (t) => (t || '').replace(/\s+/g, ' ').trim().toLowerCase();
  // «marco»: el elemento se busca dentro de un iframe del mismo origen (los paneles de la app de
  // escritorio). Las coordenadas se pasan al documento principal sumando la posición del iframe.
  cc.off = { x: 0, y: 0 };
  cc.doc = (marco) => {
    if (!marco) { cc.off = { x: 0, y: 0 }; return document; }
    const f = [...document.querySelectorAll(marco)].find((x) => visible(x) && x.contentDocument);
    if (!f) return null;
    const r = f.getBoundingClientRect();
    cc.off = { x: r.left + f.clientLeft, y: r.top + f.clientTop };
    return f.contentDocument;
  };
  cc.texto = (marco) => { const d = cc.doc(marco); return d && d.body ? d.body.innerText : ''; };
  const porTextoPropio = (base, t) => {
    // El elemento más pequeño cuyo propio texto contiene el buscado (para resaltar o señalar textos).
    const w = (base.ownerDocument || base).createTreeWalker(base.nodeType === 9 ? base.body : base, NodeFilter.SHOW_TEXT);
    let n; while ((n = w.nextNode())) { const p = n.parentElement; if (p && norm(n.nodeValue).includes(t) && visible(p) && !p.closest('#__cc')) return p; }
    // El texto puede estar repartido entre varios nodos (<strong>2</strong> por validar).
    const todos = [...base.querySelectorAll('*')].filter((e) => !e.closest('#__cc') && visible(e) && norm(e.innerText).includes(t));
    todos.sort((a, b) => norm(a.innerText).length - norm(b.innerText).length);
    return todos[0] || null;
  };
  cc.buscar = (sel, texto, dentro, modo, cerca, marco) => {
    const doc = cc.doc(marco);
    if (!doc) return null;
    const base = dentro ? doc.querySelector(dentro) : doc;
    if (!base) return null;
    let el = null;
    if (sel) el = [...base.querySelectorAll(sel)].find(visible) || null;
    else if (texto) {
      const t = norm(texto);
      if (modo !== 'texto') {
        const area = innerWidth * innerHeight * 0.3;
        const cands = [...base.querySelectorAll('button, a, [role=button], [role=tab], [role=menuitem], [role=option], [role=link], [role=checkbox], [role=radio], label, summary, li, .tarjeta, input[type=submit], [tabindex]:not([tabindex="-1"])')]
          .filter((e) => !e.closest('#__cc') && visible(e) && e.getBoundingClientRect().width * e.getBoundingClientRect().height < area
            && norm(e.innerText || e.value || e.getAttribute('aria-label')).includes(t));
        const txt = (e) => norm(e.innerText || e.value || e.getAttribute('aria-label'));
        cands.sort((a, b) => (txt(a) === t ? 0 : 1) - (txt(b) === t ? 0 : 1) || txt(a).length - txt(b).length);
        el = cands[0] || null;
      }
      if (!el) el = porTextoPropio(base, t);
    }
    if (el && cerca) el = el.closest(cerca) || el;
    cc.ultimo = el;
    return el ? cc.rect(el) : null;
  };
  cc.rect = (el) => {
    const r = el.getBoundingClientRect();
    const o = el.ownerDocument === document ? { x: 0, y: 0 } : cc.off;
    return { x: r.left + o.x, y: r.top + o.y, w: r.width, h: r.height, vw: innerWidth, vh: innerHeight };
  };
  cc.centrar = () => { if (cc.ultimo) cc.ultimo.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' }); };
  montar();
})();`

// ---------- Navegador y CDP ----------
async function abrirNavegador({ ancho, alto, microfono }) {
  const navegador = opt('navegador') ?? NAVEGADORES.find((p) => existsSync(p))
  if (!navegador) throw new Error('No encuentro Edge ni Chrome')
  const puerto = await puertoLibre()
  const perfil = mkdtempSync(join(tmpdir(), 'cidia-grabador-'))
  const flags = [
    '--headless=new', `--remote-debugging-port=${puerto}`, `--user-data-dir=${perfil}`,
    '--no-first-run', '--no-default-browser-check', '--hide-scrollbars', '--mute-audio',
    '--disable-component-update', '--disable-background-networking', '--disable-sync', '--disk-cache-size=1',
    '--disable-extensions', '--no-pings', '--disable-features=Translate,EdgeCollections,msEdgeShopping,AutofillServerCommunication',
    '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required',
    '--force-color-profile=srgb', '--font-render-hinting=none', '--lang=es-ES', '--accept-lang=es-ES,es',
    `--window-size=${ancho},${alto}`,
  ]
  if (microfono) flags.push(`--use-file-for-fake-audio-capture=${microfono}%noloop`)
  flags.push('about:blank')
  const proc = spawn(navegador, flags, { stdio: 'ignore' })
  let destino
  for (let i = 0; i < 80 && !destino; i++) {
    try { destino = (await (await fetch(`http://127.0.0.1:${puerto}/json/list`)).json()).find((d) => d.type === 'page') } catch { /* arrancando */ }
    if (!destino) await dormir(250)
  }
  if (!destino) throw new Error('El navegador no arranca')
  return {
    ws: destino.webSocketDebuggerUrl,
    cerrar: async () => {
      try {
        const v = await (await fetch(`http://127.0.0.1:${puerto}/json/version`)).json()
        const wb = new WebSocket(v.webSocketDebuggerUrl)
        await new Promise((ok) => { wb.onopen = ok; wb.onerror = ok; setTimeout(ok, 1500) })
        try { wb.send(JSON.stringify({ id: 1, method: 'Browser.close' })) } catch { /* ya cerrado */ }
        await dormir(800)
        try { wb.close() } catch { /* nada */ }
      } catch { /* ya cerrado */ }
      // Edge deja procesos hijos: se cierra el árbol entero del proceso que hemos lanzado (y solo ese).
      if (process.platform === 'win32') {
        spawnSync('taskkill', ['/PID', String(proc.pid), '/T', '/F'], { stdio: 'ignore' })
        // Por si algún proceso hijo se ha quedado colgado del árbol: los de este perfil temporal (y solo esos).
        const nombre = perfil.split(/[\\/]/).pop()
        spawnSync('powershell', ['-NoProfile', '-Command', `Get-CimInstance Win32_Process -Filter "Name='${basenameNavegador(navegador)}'" | Where-Object { $_.CommandLine -like '*${nombre}*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }`], { stdio: 'ignore' })
      } else { try { proc.kill('SIGKILL') } catch { /* nada */ } }
      for (let i = 0; i < 12; i++) { try { rmSync(perfil, { recursive: true, force: true }); break } catch { await dormir(500) } }
    },
  }
}

async function conectarExistente(puerto, filtro) {
  const lista = await (await fetch(`http://127.0.0.1:${puerto}/json/list`)).json()
  const destino = lista.find((d) => d.type === 'page' && (!filtro || d.url.includes(filtro))) ?? lista.find((d) => d.type === 'page')
  if (!destino) throw new Error(`No hay ninguna página en el puerto ${puerto}`)
  return { ws: destino.webSocketDebuggerUrl, cerrar: async () => { /* no se cierra lo que no hemos abierto */ } }
}

function clienteCdp(url) {
  const ws = new WebSocket(url)
  let n = 0
  const pend = new Map()
  const oyentes = new Map()
  const abierto = new Promise((ok, mal) => { ws.onopen = ok; ws.onerror = mal })
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data)
    if (d.id && pend.has(d.id)) { const p = pend.get(d.id); pend.delete(d.id); d.error ? p.mal(new Error(d.error.message)) : p.ok(d.result); return }
    for (const f of oyentes.get(d.method) ?? []) f(d.params)
  }
  return {
    abierto,
    enviar: (method, params = {}) => new Promise((ok, mal) => { const i = ++n; pend.set(i, { ok, mal }); ws.send(JSON.stringify({ id: i, method, params })) }),
    on: (ev, f) => { if (!oyentes.has(ev)) oyentes.set(ev, []); oyentes.get(ev).push(f) },
    cerrar: () => { try { ws.close() } catch { /* nada */ } },
  }
}

// Duración de un WAV PCM (para mantener pulsado el micrófono lo que dura la pregunta).
function duracionWav(f) {
  const b = readFileSync(f)
  let i = 12, tasa = 0
  while (i + 8 <= b.length) {
    const id = b.toString('ascii', i, i + 4), n = b.readUInt32LE(i + 4)
    if (id === 'fmt ') tasa = b.readUInt32LE(i + 16) // bytes por segundo
    if (id === 'data' && tasa) return Math.round((Math.min(n, b.length - i - 8) / tasa) * 1000)
    i += 8 + n + (n % 2)
  }
  throw new Error(`No entiendo el WAV ${f}`)
}

// ---------- Rutas con marcadores ----------
function rutaDe(p, dirEscena) {
  if (!p) return p
  const r = p.replaceAll('{repo}', REPO).replaceAll('{voces}', VOCES).replaceAll('{salida}', SALIDA).replaceAll('{escena}', dirEscena)
  return isAbsolute(r) ? r : resolve(dirEscena, r)
}

// ---------- Grabar una escena ----------
async function grabarEscena(escena, dirEscena) {
  const escala = Number(escena.escala ?? 1)
  const anchoFisico = Number(escena.ancho ?? 1920), altoFisico = Number(escena.alto ?? 1080)
  const ancho = Math.round(anchoFisico / escala), alto = Math.round(altoFisico / escala)
  const microfono = escena.microfono ? rutaDe(escena.microfono, dirEscena) : null
  if (microfono && !existsSync(microfono)) throw new Error(`No existe el audio del micrófono: ${microfono}`)
  const informe = { id: escena.id, usuario: escena.usuario ?? null, ruta: escena.ruta, ancho: anchoFisico, alto: altoFisico, escala,
    marcas: [], acciones: [], esperas: [], fallos: [], consola: [], excepciones: [], peticiones_fallidas: [] }
  const carpetaFotos = join(SALIDA, `.fotogramas-${escena.id}`)
  rmSync(carpetaFotos, { recursive: true, force: true })
  mkdirSync(carpetaFotos, { recursive: true })

  // Ventana ya abierta (la app de escritorio con --remote-debugging-port): --conectar o "conectar" en la escena.
  const puertoConectar = CONECTAR ?? escena.conectar?.puerto
  const conectado = !!puertoConectar
  const cursorManual = conectado || escena.contexto === 'app'
  const nav = conectado ? await conectarExistente(puertoConectar, opt('objetivo') ?? escena.conectar?.objetivo) : await abrirNavegador({ ancho: anchoFisico, alto: altoFisico, microfono })
  const cdp = clienteCdp(nav.ws)
  const fotos = [] // { f, t } con t en segundos
  let grabando = false
  let idScript
  try {
    await cdp.abierto
    // Errores de la página: sirven para no montar escenas con fallos en pantalla.
    cdp.on('Runtime.consoleAPICalled', (p) => { if (['error', 'warning'].includes(p.type)) informe.consola.push(ocultar(`${p.type}: ` + p.args.map((a) => a.value ?? a.description ?? '').join(' ')).slice(0, 300)) })
    cdp.on('Runtime.exceptionThrown', (p) => informe.excepciones.push(ocultar(p.exceptionDetails.exception?.description ?? p.exceptionDetails.text).slice(0, 400)))
    let pendientesRed = 0, ultimaRed = Date.now()
    const enVuelo = new Set()
    cdp.on('Network.requestWillBeSent', (p) => { enVuelo.add(p.requestId); pendientesRed = enVuelo.size; ultimaRed = Date.now() })
    const fin = (p) => { enVuelo.delete(p.requestId); pendientesRed = enVuelo.size; ultimaRed = Date.now() }
    cdp.on('Network.loadingFinished', fin)
    cdp.on('Network.loadingFailed', (p) => { if (!p.canceled && p.type !== 'EventSource') informe.peticiones_fallidas.push(`fallo de red ${p.errorText}`); fin(p) })
    cdp.on('Network.responseReceived', (p) => { if (p.response.status >= 400) informe.peticiones_fallidas.push(ocultar(`${p.response.status} ${p.response.url}`).slice(0, 220)) })
    let numFoto = 0
    cdp.on('Page.screencastFrame', (p) => {
      cdp.enviar('Page.screencastFrameAck', { sessionId: p.sessionId }).catch(() => {})
      if (!grabando) return
      const f = join(carpetaFotos, `f${String(++numFoto).padStart(6, '0')}.jpg`)
      writeFileSync(f, Buffer.from(p.data, 'base64'))
      fotos.push({ f, t: p.metadata.timestamp ?? Date.now() / 1000 })
    })
    let selectorFichero = null
    cdp.on('Page.fileChooserOpened', (p) => { selectorFichero = p })

    await cdp.enviar('Runtime.enable'); await cdp.enviar('Network.enable'); await cdp.enviar('Page.enable'); await cdp.enviar('DOM.enable')
    if (!conectado) {
      await cdp.enviar('Emulation.setDeviceMetricsOverride', { width: ancho, height: alto, deviceScaleFactor: escala, mobile: false })
      await cdp.enviar('Emulation.setFocusEmulationEnabled', { enabled: true })
      await cdp.enviar('Browser.grantPermissions', { permissions: ['audioCapture', 'videoCapture'], origin: BASE }).catch(() => {})
    } else if (escena.emular !== false) {
      // La ventana real tiene el tamaño de la pantalla: se graba a 1920x1080 emulando el área de la página
      // (al terminar se quita y la ventana vuelve a su tamaño).
      await cdp.enviar('Emulation.setDeviceMetricsOverride', { width: ancho, height: alto, deviceScaleFactor: escala, mobile: false })
      await cdp.enviar('Emulation.setFocusEmulationEnabled', { enabled: true }).catch(() => {})
    }
    idScript = (await cdp.enviar('Page.addScriptToEvaluateOnNewDocument', { source: SCRIPT_PAGINA })).identifier

    const evaluar = async (expr) => {
      const r = await cdp.enviar('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })
      if (r.exceptionDetails) throw new Error(ocultar(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text))
      return r.result?.value
    }
    const redQuieta = async (quieto = 600, max = 15000) => {
      const t0 = Date.now()
      while (Date.now() - t0 < max) { if (pendientesRed === 0 && Date.now() - ultimaRed > quieto) return; await dormir(100) }
    }

    // Carga inicial (sin grabar): sesión por token en el hash, fuentes y datos cargados.
    let url = BASE + (escena.ruta ?? '/app/')
    if (escena.usuario) url += (url.includes('#') ? '&' : '#') + 'token=' + encodeURIComponent(await tokenDe(escena.usuario))
    if (!conectado || escena.ruta) {
      await cdp.enviar('Page.navigate', { url })
      await dormir(400)
    }
    await evaluar(SCRIPT_PAGINA)
    await redQuieta(700, 20000)
    await evaluar('document.fonts ? document.fonts.ready.then(() => true) : true')
    if (escena.esperar_inicio) {
      const t0 = Date.now()
      while (Date.now() - t0 < 30000 && !(await evaluar(`document.body.innerText.includes(${JSON.stringify(escena.esperar_inicio)})`))) await dormir(200)
    }
    // "antes_js": se evalúa antes de empezar a grabar (por ejemplo, un estilo para ocultar algo que no
    // es de la escena). Lo que se meta dentro de #__cc desaparece al terminar.
    if (escena.antes_js) informe.antes_js = await evaluar(escena.antes_js)
    if (escena.ocultar_css) await evaluar(`(() => { const s = document.createElement('style'); s.textContent = ${JSON.stringify(escena.ocultar_css)} + '{display:none!important}'; document.getElementById('__cc').appendChild(s); return true })()`)
    await dormir(Number(escena.asentar_ms ?? 600))

    // Cursor: posición inicial y movimiento suave con eventos de puntero reales.
    let pos = escena.cursor_inicio ?? [Math.round(ancho * 0.62), Math.round(alto * 0.58)]
    let pulsado = false
    const raton = (type, x, y, extra = {}) => cdp.enviar('Input.dispatchMouseEvent', { type, x, y, button: extra.button ?? (pulsado ? 'left' : 'none'), buttons: pulsado ? 1 : 0, pointerType: 'mouse', ...extra })
    await raton('mouseMoved', pos[0], pos[1])
    await evaluar(`window.__cc && window.__cc.mover(${pos[0]}, ${pos[1]})`)
    if (escena.cursor === false) await evaluar('window.__cc && window.__cc.mostrar(false)')

    const suave = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
    async function moverA(x, y, durMs) {
      const [x0, y0] = pos
      const d = Math.hypot(x - x0, y - y0)
      if (d < 2) { pos = [x, y]; return }
      const T = durMs ?? Math.min(1050, Math.max(320, 240 + d * 0.5))
      // Trayectoria ligeramente curva (Bézier cuadrática), como la de una mano.
      const nx = -(y - y0) / d, ny = (x - x0) / d, desvio = Math.min(60, d * 0.1) * (x > x0 ? 1 : -1)
      const cx = (x0 + x) / 2 + nx * desvio, cy = (y0 + y) / 2 + ny * desvio
      const t0 = Date.now()
      for (;;) {
        const t = Math.min(1, (Date.now() - t0) / T), e = suave(t)
        const px = (1 - e) * (1 - e) * x0 + 2 * (1 - e) * e * cx + e * e * x
        const py = (1 - e) * (1 - e) * y0 + 2 * (1 - e) * e * cy + e * e * y
        await raton('mouseMoved', px, py)
        // Sobre un iframe los eventos de puntero no llegan al documento principal: se mueve a mano.
        if (cursorManual) await evaluar(`window.__cc && window.__cc.mover(${px.toFixed(1)}, ${py.toFixed(1)})`)
        if (t >= 1) break
        await dormir(14)
      }
      pos = [x, y]
    }
    // Busca el elemento (esperando a que aparezca), lo centra con desplazamiento suave si hace falta
    // y devuelve el punto al que apuntar.
    async function localizar(a, { selector, texto, dentro, modo }, maxMs = 10000) {
      const t0 = Date.now()
      let r = null
      const q = [selector, texto, dentro, modo, a.cerca, a.marco].map((v) => JSON.stringify(v ?? null)).join(', ')
      while (Date.now() - t0 < maxMs) {
        r = await evaluar(`window.__cc.buscar(${q})`)
        if (r) break
        await dormir(200)
      }
      if (!r) throw new Error(`no encuentro ${selector ? 'el selector ' + selector : '«' + texto + '»'}`)
      const margen = 70
      if (r.y < margen || r.y + Math.min(r.h, r.vh * 0.6) > r.vh - margen || r.x < 0 || r.x + r.w > r.vw) {
        await evaluar('window.__cc.centrar()')
        // El desplazamiento suave tarda un poco en empezar: se espera y luego a que la posición no cambie
        // en tres lecturas seguidas (si no, se pulsaría donde estaba el elemento antes de moverse).
        await dormir(180)
        let previo = '', iguales = 0
        for (let i = 0; i < 50 && iguales < 3; i++) {
          await dormir(60)
          const k = JSON.stringify(await evaluar('window.__cc.ultimo ? window.__cc.rect(window.__cc.ultimo) : null'))
          iguales = k === previo ? iguales + 1 : 0
          previo = k
        }
        r = JSON.parse(previo) ?? r
        await dormir(120)
      }
      const fx = a.punto?.[0] ?? (r.w > 520 ? 0.3 : 0.5), fy = a.punto?.[1] ?? 0.5
      return { x: Math.round(r.x + r.w * fx), y: Math.round(r.y + Math.min(r.h, 120) * fy), r }
    }
    async function pulsar(x, y, doble = false) {
      await dormir(90)
      if (cursorManual) await evaluar(`window.__cc && window.__cc.onda(${x}, ${y})`)
      pulsado = true
      await raton('mousePressed', x, y, { button: 'left', clickCount: 1 })
      await dormir(85)
      pulsado = false
      await raton('mouseReleased', x, y, { button: 'left', clickCount: 1 })
      if (doble) {
        await dormir(70); pulsado = true
        await raton('mousePressed', x, y, { button: 'left', clickCount: 2 }); await dormir(70); pulsado = false
        await raton('mouseReleased', x, y, { button: 'left', clickCount: 2 })
      }
    }
    const TECLAS = { Enter: [13, '\r'], Tab: [9, ''], Escape: [27, ''], Backspace: [8, ''], Delete: [46, ''], ArrowDown: [40, ''], ArrowUp: [38, ''], ArrowLeft: [37, ''], ArrowRight: [39, ''], Space: [32, ' '], Home: [36, ''], End: [35, ''], PageDown: [34, ''], PageUp: [33, ''] }
    async function tecla(combo) {
      const partes = combo.split('+'), k = partes.pop()
      const mod = (partes.includes('Alt') ? 1 : 0) | (partes.includes('Control') ? 2 : 0) | (partes.includes('Meta') ? 4 : 0) | (partes.includes('Shift') ? 8 : 0)
      const [vk, texto] = TECLAS[k] ?? [k.length === 1 ? k.toUpperCase().charCodeAt(0) : 0, k.length === 1 && !mod ? k : '']
      const code = TECLAS[k] ? (k === 'Space' ? 'Space' : k) : (k.length === 1 ? (/[a-z]/i.test(k) ? 'Key' + k.toUpperCase() : /\d/.test(k) ? 'Digit' + k : '') : k)
      const key = k === 'Space' ? ' ' : k
      await cdp.enviar('Input.dispatchKeyEvent', { type: texto ? 'keyDown' : 'rawKeyDown', key, code, windowsVirtualKeyCode: vk, modifiers: mod, text: texto || undefined })
      await cdp.enviar('Input.dispatchKeyEvent', { type: 'keyUp', key, code, windowsVirtualKeyCode: vk, modifiers: mod })
    }
    async function rueda(total, enX, enY) {
      const pasos = Math.max(8, Math.round(Math.abs(total) / 28))
      let hecho = 0
      for (let i = 1; i <= pasos; i++) {
        const objetivo = Math.round(total * suave(i / pasos))
        await cdp.enviar('Input.dispatchMouseEvent', { type: 'mouseWheel', x: enX, y: enY, deltaX: 0, deltaY: objetivo - hecho, pointerType: 'mouse' })
        hecho = objetivo
        await dormir(16)
      }
    }
    async function esperarCondicion(expr, maxMs) {
      const t0 = Date.now()
      while (Date.now() - t0 < maxMs) { if (await evaluar(expr)) return true; await dormir(200) }
      return false
    }

    // ---------- Sincronía con la narración ----------
    // Si la voz de la escena ya está sintetizada (voz.py narrar), el grabador espera en directo en cada
    // marca a que termine el fragmento anterior, con las mismas reglas que montaje.py (hueco entre
    // fragmentos, desfase y esperas largas que el montaje acelerará). Así el vídeo ya sale al ritmo de
    // la voz y el montaje no tiene que congelar la imagen.
    const vozF = join(VOCES, `${escena.id}.json`)
    const frags = escena.sincronizar_voz !== false && !flag('sin-sincronizar-voz') && existsSync(vozF)
      ? JSON.parse(readFileSync(vozF, 'utf8')).fragmentos ?? [] : []
    const P = { hueco: Number(escena.hueco_voz_s ?? 0.35), inicio: Number(escena.inicio_voz_s ?? 0.6), desfase: 0.15,
      umbral: Number(escena.umbral_espera_s ?? 2.5), objetivo: Number(escena.espera_objetivo_s ?? 1.8), cola: Number(escena.cola_voz_s ?? 1.0) }
    let kf = 0, finVoz = null, ahorro = 0
    informe.esperas_voz = []
    const colocarVoz = (marca, tSalida) => {
      // Coloca los fragmentos hasta el de esta marca; devuelve cuánto hay que esperar (s).
      while (kf < frags.length) {
        const fr = frags[kf]
        if (fr.marca && fr.marca !== marca && marca !== null) return 0
        const iniMin = finVoz == null ? P.inicio : finVoz + (fr.tras || P.hueco)
        let espera = 0
        if (marca !== null && fr.marca === marca) {
          const ancla = tSalida + P.desfase
          if (iniMin > ancla + 0.2) espera = iniMin - ancla
          finVoz = Math.max(ancla + espera, iniMin) + fr.duracion
          kf++
          return espera
        }
        finVoz = iniMin + fr.duracion
        kf++
      }
      return 0
    }
    const contarEspera = (e) => {
      const d = (e.fin - e.inicio) / 1000
      if (e.acelerar !== false && d > P.umbral && d / P.objetivo >= 1.4) ahorro += d - P.objetivo
    }

    // ---------- A grabar ----------
    await cdp.enviar('Page.startScreencast', { format: 'jpeg', quality: CALIDAD, maxWidth: anchoFisico, maxHeight: altoFisico, everyNthFrame: 1 })
    grabando = true
    const tArranque = Date.now()
    while (!fotos.length && Date.now() - tArranque < 5000) { await raton('mouseMoved', pos[0], pos[1]); await dormir(50) }
    const t0 = fotos.length ? fotos[0].t * 1000 : Date.now()
    const ahora = () => Math.round(Date.now() - t0)
    await dormir(Number(escena.colchon_inicial_ms ?? 500))

    for (const [i, a] of (escena.acciones ?? []).entries()) {
      const tipo = Object.keys(a).find((k) => !['pausa', 'max', 'acelerar', 'dentro', 'limpiar', 'ms_tecla', 'doble', 'punto', 'ms', 'nota', 'en', 'recargar', 'obligatorio', 'clic', 'clicTexto', 'input', 'cerca', 'oscurecer', 'marco'].includes(k)) ?? (a.clic ? 'clic' : a.clicTexto ? 'clicTexto' : '?')
      const reg = { i, tipo, inicio: ahora() }
      let pausa = 0
      try {
        if (tipo === 'marca') {
          const espera = frags.length ? colocarVoz(a.marca, ahora() / 1000 - ahorro) : 0
          if (espera > 0) { informe.esperas_voz.push({ marca: a.marca, ms: Math.round(espera * 1000) }); await dormir(espera * 1000) }
          informe.marcas.push({ nombre: a.marca, t: ahora() })
        }
        else if (tipo === 'esperar') {
          // Con "acelerar" (texto del rótulo), la pausa queda marcada como espera y el montaje la acelera
          // avisándolo (por ejemplo, mientras alguien graba una nota de voz larga).
          const ini = ahora()
          await dormir(a.esperar)
          if (a.acelerar) { const espera = { accion: i, tipo, objetivo: a.esperar, inicio: ini, fin: ahora(), acelerar: a.acelerar }; informe.esperas.push(espera); contarEspera(espera) }
        }
        else if (tipo === 'esperarVoz') {
          // Espera a que termine la narración colocada hasta aquí (para que, por ejemplo, la pregunta por
          // voz no se pise con la voz del narrador).
          if (frags.length && finVoz != null) {
            const resto = finVoz + P.hueco - (ahora() / 1000 - ahorro)
            if (resto > 0) { informe.esperas_voz.push({ marca: 'esperarVoz', ms: Math.round(resto * 1000) }); await dormir(resto * 1000) }
          }
        }
        else if (tipo === 'microfono') {
          // Marca el momento en que el micrófono empieza a «oír» el WAV (botón de pulsar para grabar).
          ;(informe.micro ??= []).push({ t: ahora(), ms: microfono ? duracionWav(microfono) : null })
        }
        else if (tipo === 'clic' || tipo === 'clicTexto' || tipo === 'hover' || tipo === 'hoverTexto') {
          const p = await localizar(a, { selector: a.clic ?? a.hover, texto: a.clicTexto ?? a.hoverTexto, dentro: a.dentro, modo: tipo === 'hoverTexto' ? 'texto' : null }, a.max ?? 10000)
          await moverA(p.x, p.y)
          if (tipo.startsWith('clic')) await pulsar(p.x, p.y, a.doble)
          pausa = 350
        } else if (tipo === 'escribir') {
          const [sel, plantilla] = a.escribir
          // {contrasena}: la de la cuenta de la escena («cuenta_acceso»), tecleada en un campo de tipo
          // password (se ven puntos). Nunca va al informe ni a la consola.
          const texto = plantilla.includes('{contrasena}') ? plantilla.replaceAll('{contrasena}', contrasenaDe(escena.cuenta_acceso ?? escena.usuario)) : plantilla
          const p = await localizar(a, { selector: sel }, a.max ?? 10000)
          await moverA(p.x, p.y)
          await pulsar(p.x, p.y)
          if (a.limpiar) await evaluar(`(() => { const e = window.__cc.ultimo; const d = Object.getOwnPropertyDescriptor(e.__proto__, 'value'); if (d && d.set) { d.set.call(e, ''); e.dispatchEvent(new Event('input', { bubbles: true })) } })()`)
          await dormir(150)
          for (const ch of texto) {
            if (ch === '\n') await tecla('Enter')
            else await cdp.enviar('Input.insertText', { text: ch })
            const base = a.ms_tecla ?? 52
            await dormir(base + Math.random() * base * 0.8 + (ch === ' ' ? base * 0.4 : 0) + (/[,.;:¿?]/.test(ch) ? base * 1.5 : 0))
          }
          pausa = 300
        } else if (tipo === 'tecla') { await tecla(a.tecla); pausa = 300 }
        else if (tipo === 'seleccionar') {
          const [sel, valor] = a.seleccionar
          const p = await localizar(a, { selector: sel }, a.max ?? 10000)
          await moverA(p.x, p.y)
          await evaluar(`window.__cc.onda(${p.x}, ${p.y})`)
          const ok = await evaluar(`(() => { const e = window.__cc.ultimo; const v = ${JSON.stringify(String(valor))};
            const o = [...e.options].find((o) => o.value === v) || [...e.options].find((o) => o.text.trim().toLowerCase().includes(v.toLowerCase()));
            if (!o) return false; const d = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value'); d.set.call(e, o.value);
            e.dispatchEvent(new Event('input', { bubbles: true })); e.dispatchEvent(new Event('change', { bubbles: true })); return true })()`)
          if (!ok) throw new Error(`no hay la opción «${valor}»`)
          pausa = 400
        } else if (tipo === 'subir') {
          const fichero = rutaDe(a.subir, dirEscena)
          if (!existsSync(fichero)) throw new Error(`no existe ${fichero}`)
          await cdp.enviar('Page.setInterceptFileChooserDialog', { enabled: true })
          selectorFichero = null
          if (a.clic || a.clicTexto) {
            const p = await localizar(a, { selector: a.clic, texto: a.clicTexto, dentro: a.dentro }, a.max ?? 10000)
            await moverA(p.x, p.y)
            await pulsar(p.x, p.y)
            const tq = Date.now()
            while (!selectorFichero && Date.now() - tq < 5000) await dormir(50)
          }
          if (selectorFichero) await cdp.enviar('DOM.setFileInputFiles', { files: [fichero], backendNodeId: selectorFichero.backendNodeId })
          else {
            const { root } = await cdp.enviar('DOM.getDocument', { depth: -1, pierce: true })
            const { nodeId } = await cdp.enviar('DOM.querySelector', { nodeId: root.nodeId, selector: a.input ?? 'input[type=file]' })
            if (!nodeId) throw new Error('no hay ningún selector de ficheros')
            await cdp.enviar('DOM.setFileInputFiles', { files: [fichero], nodeId })
          }
          await cdp.enviar('Page.setInterceptFileChooserDialog', { enabled: false })
          pausa = 500
        } else if (tipo === 'esperarTexto' || tipo === 'esperarSinTexto' || tipo === 'esperarSelector' || tipo === 'esperarJs') {
          const v = JSON.stringify(a[tipo])
          const m = JSON.stringify(a.marco ?? null)
          const txt = `(window.__cc ? window.__cc.texto(${m}) : (document.body ? document.body.innerText : ''))`
          const doc = `((window.__cc ? window.__cc.doc(${m}) : document) || { querySelector: () => null })`
          const expr = tipo === 'esperarTexto' ? `${txt}.includes(${v})`
            : tipo === 'esperarSinTexto' ? `!${txt}.includes(${v})` : tipo === 'esperarJs' ? `!!(() => { try { return (${a.esperarJs}) } catch { return false } })()` : `!!${doc}.querySelector(${v})`
          const ini = ahora()
          const ok = await esperarCondicion(expr, a.max ?? 30000)
          const espera = { accion: i, tipo, objetivo: a[tipo], inicio: ini, fin: ahora(), acelerar: a.acelerar ?? true }
          informe.esperas.push(espera)
          contarEspera(espera)
          if (!ok) throw new Error(`pasados ${a.max ?? 30000} ms sigue sin cumplirse ${tipo} ${v}`)
          pausa = 250
        } else if (tipo === 'mantenerMicro') {
          const [sel, msPedido] = a.mantenerMicro
          if ((msPedido === 'auto' || msPedido == null) && !microfono) throw new Error('mantenerMicro "auto" necesita "microfono" en la escena')
          const ms = msPedido === 'auto' || msPedido == null ? duracionWav(microfono) + 350 : Number(msPedido)
          reg.mantener_ms = ms
          const p = await localizar(a, { selector: sel }, a.max ?? 10000)
          await moverA(p.x, p.y)
          await dormir(150)
          pulsado = true
          await raton('mousePressed', p.x, p.y, { button: 'left', clickCount: 1 })
          await evaluar('window.__cc.halo(true)')
          const iniMicro = ahora()
          ;(informe.micro ??= []).push({ t: iniMicro, ms: microfono ? duracionWav(microfono) : null })
          const tq = Date.now()
          while (Date.now() - tq < ms) { await raton('mouseMoved', p.x, p.y); await dormir(100) }
          pulsado = false
          await raton('mouseReleased', p.x, p.y, { button: 'left', clickCount: 1 })
          await evaluar('window.__cc.halo(false)')
          if (a.acelerar) { const espera = { accion: i, tipo, objetivo: 'micrófono', inicio: iniMicro, fin: ahora(), acelerar: a.acelerar }; informe.esperas.push(espera); contarEspera(espera) }
          pausa = 300
        } else if (tipo === 'scroll') {
          if (typeof a.scroll === 'string') {
            await localizar({}, { selector: a.scroll }, a.max ?? 10000)
            await evaluar('window.__cc.centrar()')
            await dormir(700)
          } else {
            if (a.en) { const p = await localizar(a, { selector: a.en }); await moverA(p.x, p.y) }
            await rueda(Number(a.scroll), pos[0], pos[1])
            await dormir(250)
          }
          pausa = 300
        } else if (tipo === 'resaltar' || tipo === 'resaltarTexto') {
          const p = await localizar(a, { selector: a.resaltar, texto: a.resaltarTexto, dentro: a.dentro, modo: 'texto' }, a.max ?? 10000)
          await evaluar(`window.__cc.oscurecer = ${a.oscurecer === false ? 'false' : 'true'}; window.__cc.resaltar(${JSON.stringify(p.r)}, ${JSON.stringify(a.nota ?? '')})`)
          await dormir(a.ms ?? 1800)
          await evaluar('window.__cc.resaltar(null)')
          pausa = 350
        } else if (tipo === 'cursor') await evaluar(`window.__cc.mostrar(${a.cursor ? 'true' : 'false'})`)
        else if (tipo === 'ir') {
          if (a.recargar) {
            await cdp.enviar('Page.navigate', { url: BASE + a.ir })
            await dormir(300)
            await redQuieta(600, 15000)
            await raton('mouseMoved', pos[0], pos[1])
          } else {
            await evaluar(`(() => { history.pushState({}, '', ${JSON.stringify(a.ir)}); dispatchEvent(new PopStateEvent('popstate', { state: {} })); return true })()`)
            await redQuieta(500, 15000)
          }
          pausa = 400
        } else if (tipo === 'eval') reg.valor = await evaluar(a.eval)
        else throw new Error(`acción desconocida: ${JSON.stringify(a)}`)
      } catch (e) {
        reg.error = String(e.message ?? e)
        informe.fallos.push(`acción ${i} (${tipo}): ${reg.error}`)
        if (a.obligatorio) { reg.fin = ahora(); informe.acciones.push(reg); break }
      }
      await dormir(a.pausa ?? pausa)
      reg.fin = ahora()
      informe.acciones.push(reg)
    }
    let minimo = Number(escena.duracion_minima_ms ?? 0)
    if (frags.length) {
      colocarVoz(null, 0) // los fragmentos que quedan van seguidos
      informe.voz_hasta_ms = Math.round((finVoz + ahorro) * 1000)
      minimo = Math.max(minimo, Math.round((finVoz + P.cola + ahorro) * 1000))
    }
    while (ahora() < minimo) await dormir(50)
    await dormir(Number(escena.colchon_final_ms ?? 400))
    const tFin = Date.now() / 1000
    grabando = false
    await cdp.enviar('Page.stopScreencast').catch(() => {})
    informe.duracion_ms = Math.round(tFin * 1000 - t0)
    informe.fotogramas = fotos.length
    informe.fps_medio = +(fotos.length / (informe.duracion_ms / 1000)).toFixed(1)
    informe.titulo = await evaluar('document.title').catch(() => null)

    // ---------- Fotogramas con su duración real -> MP4 a 30 fps ----------
    if (!flag('sin-video') && fotos.length) {
      const lista = join(carpetaFotos, 'lista.txt')
      const lineas = []
      for (let k = 0; k < fotos.length; k++) {
        const fin = k + 1 < fotos.length ? fotos[k + 1].t : tFin
        lineas.push(`file '${fotos[k].f.replaceAll('\\', '/')}'`, `duration ${Math.max(0.001, fin - fotos[k].t).toFixed(6)}`)
      }
      lineas.push(`file '${fotos[fotos.length - 1].f.replaceAll('\\', '/')}'`) // el demuxer ignora la duración del último
      writeFileSync(lista, lineas.join('\n') + '\n')
      const mp4 = join(SALIDA, `${escena.id}.mp4`)
      const r = spawnSync(FFMPEG, ['-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lista,
        '-vf', `fps=30,scale=${anchoFisico}:${altoFisico}:flags=lanczos:in_range=full:out_range=tv:in_color_matrix=bt601:out_color_matrix=bt709,format=yuv420p`,
        '-c:v', 'libopenh264', '-profile:v', 'high', '-b:v', BITRATE, '-maxrate', '40M', '-g', '60',
        '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
        '-t', (informe.duracion_ms / 1000).toFixed(3), '-movflags', '+faststart', mp4], { encoding: 'utf8' })
      if (r.status !== 0) informe.fallos.push('ffmpeg: ' + (r.stderr || r.error || '').toString().slice(0, 600))
      else informe.video = mp4
    }
  } finally {
    grabando = false
    if (conectado) {
      // La ventana sigue abierta para quien la usa: sin cursor, sin script y con su tamaño de siempre.
      await cdp.enviar('Page.stopScreencast').catch(() => {})
      await cdp.enviar('Runtime.evaluate', { expression: "document.getElementById('__cc')?.remove(); delete window.__cc" }).catch(() => {})
      if (idScript) await cdp.enviar('Page.removeScriptToEvaluateOnNewDocument', { identifier: idScript }).catch(() => {})
      await cdp.enviar('Emulation.clearDeviceMetricsOverride').catch(() => {})
      await cdp.enviar('Emulation.setFocusEmulationEnabled', { enabled: false }).catch(() => {})
    }
    cdp.cerrar()
    await nav.cerrar()
    if (!flag('conservar-fotogramas')) rmSync(carpetaFotos, { recursive: true, force: true })
  }
  writeFileSync(join(SALIDA, `${escena.id}.json`), JSON.stringify(informe, null, 2))
  return informe
}

// ---------- Escena suelta o proyecto con varias ----------
const datos = JSON.parse(readFileSync(entrada, 'utf8'))
const dirEntrada = dirname(resolve(entrada))
const escenas = []
if (Array.isArray(datos.piezas)) {
  for (const p of datos.piezas) {
    if (!p.escena || p.omitir) continue
    // La escena va en su fichero (ruta relativa al proyecto) o en línea, dentro de la propia pieza.
    if (typeof p.escena === 'object') { escenas.push([p.escena, dirEntrada]); continue }
    const f = rutaDe(p.escena, dirEntrada)
    escenas.push([JSON.parse(readFileSync(f, 'utf8')), dirname(f)])
  }
} else escenas.push([datos, dirEntrada])

let mal = 0
for (const [e, dir] of escenas) {
  if (SOLO && !SOLO.includes(e.id)) continue
  const t = Date.now()
  let inf
  try { inf = await grabarEscena(e, dir) } catch (err) { inf = { id: e.id, fallos: [String(err.message ?? err)] } }
  const problemas = (inf.fallos?.length ?? 0) + (inf.excepciones?.length ?? 0) + (inf.peticiones_fallidas?.length ?? 0)
  if (problemas) mal++
  console.log(JSON.stringify({ escena: e.id, segundos: inf.duracion_ms ? +(inf.duracion_ms / 1000).toFixed(1) : null, fps_medio: inf.fps_medio,
    tardado_s: Math.round((Date.now() - t) / 1000), video: inf.video ?? null, fallos: inf.fallos, excepciones: inf.excepciones,
    peticiones_fallidas: inf.peticiones_fallidas, consola: inf.consola?.slice(0, 5) }))
}
process.exit(mal ? 1 : 0)
