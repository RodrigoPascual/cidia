/* Director del vídeo v2 de CidIA para HyperFrames.
 *
 * Lee los datos del bloque (<script id="datos-cidia">, los escribe herramientas/video/hyperframes.py), construye
 * la composición y la pinta como función pura del tiempo: HyperFrames mueve una línea de tiempo de GSAP en pausa y
 * cada fotograma llama a pintar(t). Así el resultado es el mismo se busque el fotograma que se busque (render en
 * paralelo por trozos). Curvas, duraciones y medidas: 04_VIDEO/v2/notas/guia-estilo.md.
 */
(function () {
  'use strict';
  const D = JSON.parse(document.getElementById('datos-cidia').textContent);
  const RAIZ = document.querySelector('[data-composition-id]');
  const ICONOS = D.iconos || {};

  // ------------------------------------------------------------------ curvas (cubic-bezier como en CSS)
  function bezier(x1, y1, x2, y2) {
    const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
    const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    const sx = (t) => ((ax * t + bx) * t + cx) * t, sy = (t) => ((ay * t + by) * t + cy) * t;
    const dx = (t) => (3 * ax * t + 2 * bx) * t + cx;
    return function (x) {
      if (x <= 0) return 0;
      if (x >= 1) return 1;
      let t = x;
      for (let i = 0; i < 8; i++) {
        const e = sx(t) - x;
        if (Math.abs(e) < 1e-6) break;
        const d = dx(t);
        if (Math.abs(d) < 1e-6) break;
        t -= e / d;
      }
      let a = 0, b = 1;
      if (Math.abs(sx(t) - x) > 1e-5) {
        t = x;
        while (a < b) { const v = sx(t); if (Math.abs(v - x) < 1e-6) break; if (x > v) a = t; else b = t; t = (a + b) / 2; if (b - a < 1e-7) break; }
      }
      return sy(t);
    };
  }
  const CURVA = {
    micro: bezier(0.16, 1, 0.3, 1), entrada: bezier(0.16, 1, 0.3, 1), salida: bezier(0.7, 0, 0.84, 0),
    camara: bezier(0.65, 0, 0.35, 1), seccion: bezier(0.83, 0, 0.17, 1), lineal: (x) => x,
  };
  const lim = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const mezcla = (a, b, x) => a + (b - a) * x;
  function k(t, t0, d, c) {
    if (d <= 0) return t >= t0 ? 1 : 0;
    return CURVA[c || 'entrada'](lim((t - t0) / d));
  }
  // Opacidad de algo que entra en t0 y sale en t1 (si t1 no es null).
  function vida(t, t0, t1, din, dsal) {
    const a = k(t, t0, din || 0.45, 'entrada');
    const b = t1 == null ? 0 : k(t, t1, dsal || 0.3, 'salida');
    return { a, b, o: Math.min(lim(a / 0.6), 1 - b) };
  }

  // ------------------------------------------------------------------ DOM
  function nodo(tag, cls, padre, html) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    if (padre) padre.appendChild(e);
    return e;
  }
  function svgIcono(nombre, extra) {
    const partes = ICONOS[nombre] || [];
    const dentro = partes.map(([tag, at]) => '<' + tag + ' ' + Object.entries(at).map(([k2, v]) => k2 + '="' + v + '"').join(' ') + '/>').join('');
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ' + (extra || '') + '>' + dentro + '</svg>';
  }
  const CHECK = '<span class="check"><svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></span>';
  const MEDIO = '<svg class="medio" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10.5" fill="none" stroke="#F5A23D" stroke-width="2.2"/><path d="M12 1.5a10.5 10.5 0 0 1 0 21z" fill="#F5A23D"/></svg>';
  const CHECK_GRANDE = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="#1F8A70"/><path d="M6.5 12.5l3.8 3.8 7.4-8" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const LOGO = (lado) => '<svg width="' + lado + '" height="' + lado + '" viewBox="0 0 40 40"><rect class="lg-cuadro" width="40" height="40" rx="11" fill="#F2C200"/>' +
    '<path class="lg-arco" d="M27.4 13.6a9.2 9.2 0 1 0 0 12.8" fill="none" stroke="#1F2328" stroke-width="4.4" stroke-linecap="round"/>' +
    '<circle class="lg-punto" cx="29.2" cy="20" r="2.7" fill="#1F2328"/></svg>';
  function chipBase(b) { return '<span class="chip">' + (b.medio ? MEDIO : CHECK) + '<span>' + b.texto + '</span></span>'; }
  function avatar(p, extra) {
    const st = 'background:' + p.color + ';' + (extra || '');
    if (p.icono) return '<span class="avatar" style="' + st + '">' + svgIcono(p.icono, 'stroke="#fff"') + '</span>';
    return '<span class="avatar" style="' + st + '">' + p.iniciales + '</span>';
  }
  function chipPersona(p) { return '<div class="persona">' + avatar(p) + '<b>' + p.nombre + '</b>' + (p.rol ? '<span>' + p.rol + '</span>' : '') + '</div>'; }
  const T = (e, o, x, y, s) => {
    e.style.opacity = o;
    e.style.transform = 'translate(' + (x || 0).toFixed(2) + 'px,' + (y || 0).toFixed(2) + 'px)' + (s != null && s !== 1 ? ' scale(' + s.toFixed(4) + ')' : '');
  };
  const mostrar = (e, si) => { if (e._v !== si) { e.style.display = si ? '' : 'none'; e._v = si; } };
  function lineasMascara(padre, lineas, cls) {
    return lineas.map((l) => { const m = nodo('span', 'linea-mask', padre); const s = nodo('span', cls || '', m, l); return s; });
  }
  function revelarLineas(spans, t, t0, paso) {
    spans.forEach((s, i) => { const a = k(t, t0 + i * (paso || 0.09), 0.45, 'entrada'); s.style.transform = 'translateY(' + ((1 - a) * 105).toFixed(1) + '%)'; });
  }
  function letraALetra(e, texto, t, t0) {
    const porFot = Math.max(1, Math.ceil(texto.length / 20));
    const n = Math.max(0, Math.min(texto.length, Math.floor((t - t0) * 30) * porFot));
    if (e._n !== n) { e.textContent = texto.slice(0, n); e._n = n; }
  }
  const mmss = (s) => { s = Math.max(0, Math.floor(s + 1e-6)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };

  // ------------------------------------------------------------------ capas globales del bloque
  const fondo = nodo('div', 'capa fondo', null);
  fondo.style.backgroundImage = 'url("' + D.fondo + '")';
  RAIZ.insertBefore(fondo, RAIZ.firstChild);
  const cab = nodo('div', 'cabecera', RAIZ);
  const cabIzq = nodo('div', 'cab-izq', cab);
  const cabSec = nodo('div', 'cab-seccion', cabIzq);
  const cabPerCaja = nodo('div', '', cabIzq);
  cabPerCaja.style.position = 'relative';
  const cabPer = nodo('div', '', cabPerCaja);
  const cabPerPrevia = nodo('div', '', cabPerCaja);
  cabPerPrevia.style.cssText = 'position:absolute;left:0;top:0;';
  const cabBases = nodo('div', 'cab-bases', cab);
  const reloj = nodo('div', 'reloj', RAIZ,
    '<svg viewBox="0 0 40 40"><circle cx="20" cy="20" r="16" fill="none" stroke="#3A4048" stroke-width="4"/>' +
    '<circle class="arco" cx="20" cy="20" r="16" fill="none" stroke="#F2C200" stroke-width="4" stroke-linecap="round" transform="rotate(-90 20 20)" stroke-dasharray="100.53" stroke-dashoffset="100.53"/></svg>' +
    '<span class="factor"></span><span class="real"></span><span class="tarea"></span>');
  const relojArco = reloj.querySelector('.arco'), relojF = reloj.querySelector('.factor'), relojR = reloj.querySelector('.real'), relojT = reloj.querySelector('.tarea');
  const subsCapa = nodo('div', 'subs', RAIZ);
  const rail = nodo('div', 'rail', RAIZ);
  const pieIzq = nodo('div', 'pie-izq', RAIZ, 'Datos sintéticos · servidor de pruebas');
  const pieDer = nodo('div', 'pie-der', RAIZ, '');
  const cortina = nodo('div', 'cortinilla', RAIZ);
  const negro = nodo('div', 'negro', RAIZ);

  // Raíl de bloques (tiempos globales del vídeo).
  const segs = (D.rail || []).map((b) => {
    const s = nodo('div', 'seg', rail);
    s.style.left = b.x + 'px'; s.style.width = b.w + 'px';
    const i = nodo('i', '', s);
    return { b, s, i };
  });

  // Subtítulos.
  const subs = (D.subtitulos || []).map((c) => {
    const e = nodo('div', 'sub' + (c.tipo === 'micro' ? ' micro' : ''), subsCapa);
    if (c.tipo === 'micro') {
      // Los cortes de línea vienen fijados desde la primera palabra: la placa no cambia de forma mientras aparecen.
      e.innerHTML = '<span class="placa"><span class="quien">' + svgIcono('mic') + c.quien + '</span><span class="frase">' +
        c.palabras.map((w) => '<span class="w">' + w.w + '</span>' + (w.br ? '<br>' : ' ')).join('') + '</span></span>';
      c.ws = Array.from(e.querySelectorAll('.w'));
    } else {
      e.innerHTML = '<span class="placa">' + c.html + '</span>';
    }
    mostrar(e, false);
    return { c, e };
  });

  const PIEZAS = [];

  function pintar(t) {
    let activa = null;
    for (const x of PIEZAS) {
      const fin = x.p.ini + x.p.dur;
      const si = t >= x.p.ini - 1e-6 && (t < fin - 1e-6 || (x === PIEZAS[PIEZAS.length - 1] && t <= fin + 1e-3));
      mostrar(x.caja, si);
      if (si) { activa = x; x.pintar(t - x.p.ini); }
    }
    pintarCabecera(t, activa);
    pintarReloj(t, activa);
    pintarSubs(t);
    pintarPie(t, activa);
    pintarCortinilla(t);
    let o = D.desde_negro ? 1 - k(t, 0, 0.35, 'lineal') : 0;
    if (D.a_negro != null) o = Math.max(o, k(t, D.a_negro, 1.0, 'lineal'));
    negro.style.opacity = o;
  }

  // ---- cabecera de las escenas
  let cabId = null;
  function pintarCabecera(t, x) {
    const e = x && x.p.tipo === 'escena' ? x.p : null;
    if (!e || !e.cabecera) { cab.style.opacity = 0; return; }
    if (cabId !== e.id) {
      const c = e.cabecera;
      cabSec.innerHTML = (c.numero ? '<b>' + String(c.numero).padStart(2, '0') + '</b><i>|</i>' : '') + c.seccion;
      cabPer.innerHTML = chipPersona(c.persona);
      cabPerPrevia.innerHTML = c.persona_previa ? chipPersona(c.persona_previa) : '';
      cabBases.innerHTML = c.bases_n ? '<span class="etq">BASES</span><span class="contador">' + CHECK + '<span>' + c.bases_n + '</span></span>' : '';
      cabId = e.id;
    }
    const lt = t - e.ini;
    let o = 1;
    if (e.cabecera.entra) o = vida(lt, 0.15, null, 0.45).o;
    cab.style.opacity = o;
    // Mientras está el reloj de una espera acelerada, la parte izquierda de la cabecera se aparta.
    let r = 0;
    for (const w of e.esperas || []) r = Math.max(r, vida(lt, w.ini - 0.12, w.fin + 0.15, 0.3, 0.3).o);
    cabIzq.style.opacity = 1 - 0.85 * r;
    // Cambio de persona con el empuje: la anterior sale y entra la nueva.
    if (e.cabecera.persona_previa) {
      const s = k(lt, 0, 0.22, 'salida'), a = k(lt, 0.18, 0.45, 'entrada');
      mostrar(cabPerPrevia, s < 1);
      mostrar(cabPer, s >= 1 || lt >= 0.18);
      T(cabPerPrevia, 1 - s, -12 * s, 0);
      T(cabPer, lim(a / 0.6), 16 * (1 - a), 0);
    } else {
      mostrar(cabPerPrevia, false);
      mostrar(cabPer, true);
      T(cabPer, 1, 0, 0);
    }
  }

  // ---- reloj de las esperas aceleradas
  function realDe(u, e) {
    // Segundo real (de la grabación) a partir del segundo del montaje dentro de la espera, con sus rampas.
    const f = e.factor, d = e.rampa, R = e.real;
    if (!d) return lim(u * f, 0, R);
    const r1 = d * (1 + f) / 2, U = 2 * d + (R - 2 * r1) / f;
    if (u <= d) return u + (f - 1) * u * u / (2 * d);
    if (u <= U - d) return r1 + (u - d) * f;
    const v = Math.max(0, U - u);
    return R - (v + (f - 1) * v * v / (2 * d));
  }
  function pintarReloj(t, x) {
    const e = x && x.p.tipo === 'escena' ? x.p : null;
    let w = null;
    if (e) { const lt = t - e.ini; w = (e.esperas || []).find((s) => lt >= s.ini - 0.12 && lt <= s.fin + 0.45); }
    const barra = x ? x.caja._barra : null;
    if (!w) { reloj.style.opacity = 0; if (barra) barra.style.width = '0'; return; }
    const lt = t - e.ini;
    const v = vida(lt, w.ini - 0.12, w.fin + 0.15, 0.3, 0.3);
    reloj.style.opacity = v.o;
    reloj.style.transform = 'translateX(-50%) translateY(' + ((1 - v.a) * -10).toFixed(1) + 'px)';
    const r = realDe(lim(lt - w.ini, 0, w.fin - w.ini), w);
    relojF.textContent = '×' + (w.factor >= 10 ? Math.round(w.factor) : (Math.round(w.factor * 10) / 10).toString().replace('.', ','));
    relojR.innerHTML = mmss(r) + ' <small>/ ' + mmss(w.real) + ' reales</small>';
    relojT.textContent = w.tarea;
    relojArco.setAttribute('stroke-dashoffset', (100.53 * (1 - r / w.real)).toFixed(2));
    if (barra) barra.style.width = (100 * r / w.real).toFixed(2) + '%';
  }

  // ---- subtítulos
  // Cada subtítulo termina de salir antes de que entre el siguiente: nunca dos placas a la vez.
  subs.forEach((s, i) => {
    const sig = subs[i + 1];
    s.c.finVis = sig ? Math.min(s.c.fin, sig.c.ini - 0.13) : s.c.fin;
  });
  function pintarSubs(t) {
    for (const s of subs) {
      const c = s.c;
      const si = t >= c.ini - 0.01 && t <= c.finVis + 0.12;
      mostrar(s.e, si);
      if (!si) continue;
      const a = k(t, c.ini, 0.2, 'micro'), b = k(t, c.finVis, 0.12, 'salida');
      s.e.style.opacity = Math.min(a, 1 - b);
      s.e.style.transform = 'translateY(' + ((1 - a) * 8).toFixed(1) + 'px)';
      if (c.ws) c.ws.forEach((w, i) => { w.style.opacity = k(t, c.palabras[i].t, 0.2, 'micro'); });
    }
  }

  // ---- pie: raíl de bloques, veracidad y bloque actual
  function pintarPie(t, x) {
    const g = t + D.desde;
    const p = x ? x.p : null;
    const ver = !p || p.pie !== false;
    rail.style.opacity = ver && D.rail && D.rail.length ? 1 : 0;
    pieIzq.style.opacity = ver ? 1 : 0;
    pieDer.style.opacity = ver ? 1 : 0;
    let actual = null;
    for (const s of segs) {
      const b = s.b;
      const hecho = g >= b.fin;
      s.s.classList.toggle('hecho', hecho);
      s.i.style.width = (hecho ? 0 : 100 * lim((g - b.ini) / (b.fin - b.ini))) + '%';
      if (g >= b.ini && g < b.fin) actual = b;
    }
    const txt = actual ? actual.etiqueta : '';
    if (pieDer._t !== txt) { pieDer.textContent = txt; pieDer._t = txt; }
  }

  // ---- cortinilla: barre de izquierda a derecha y tapa del todo en el cambio
  function pintarCortinilla(t) {
    let x = null;
    for (const c of D.cortinillas || []) {
      if (t >= c - 0.3 && t <= c + 0.3) { x = mezcla(-1960, 1960, k(t, c - 0.3, 0.6, 'seccion')); break; }
    }
    if (x == null) { cortina.style.opacity = 0; return; }
    cortina.style.opacity = 1;
    cortina.style.transform = 'translateX(' + x.toFixed(1) + 'px)';
  }

  // ------------------------------------------------------------------ constructores de piezas
  function camaraEn(lista, lt) {
    let cx = 960, cy = 540, z = 1;
    for (const c of lista || []) {
      if (lt < c[0]) break;
      const a = k(lt, c[0], c[1] - c[0], 'camara');
      cx = mezcla(cx, c[2], a); cy = mezcla(cy, c[3], a); z = mezcla(z, c[4], a);
    }
    return { cx, cy, z };
  }
  function aplicarCamara(e, cam, W, H, base) {
    const s = base * cam.z;
    let tx = W / 2 - s * cam.cx, ty = H / 2 - s * cam.cy;
    tx = Math.min(0, Math.max(W - 1920 * s, tx));
    ty = Math.min(0, Math.max(H - 1080 * s, ty));
    e.style.transform = 'translate(' + tx.toFixed(2) + 'px,' + ty.toFixed(2) + 'px) scale(' + s.toFixed(5) + ')';
    return { tx, ty, s };
  }

  const CONSTRUCTORES = {
    escena(p, caja) {
      const marco = caja.querySelector('.marco');
      const camara = caja.querySelector('.camara');
      const previo = caja.querySelector('.marco-previo');
      caja._barra = caja.querySelector('.barra-real');
      let res = null, resPartes = [];
      if (p.resultado) {
        const r = p.resultado;
        res = nodo('div', 'resultado', caja);
        const pil = nodo('span', 'pildora', res, 'RESULTADO');
        const tx = nodo('div', 'res-texto', res, r.texto);
        resPartes.push(pil, tx);
        if (r.comparar) {
          const cmp = nodo('div', 'comparar' + (r.comparar.lado_a_lado ? ' lado-a-lado' : ''), res);
          for (const lado of ['antes', 'despues']) {
            const l = nodo('div', 'lado ' + (r.comparar[lado].tono || ''), cmp, '<span class="nombre">' + r.comparar[lado].etiqueta + '</span><div class="img"><img src="' + r.comparar[lado].img + '"></div>');
            resPartes.push(l);
          }
        }
        if (r.iluo) {
          const il = nodo('div', 'iluo', res);
          nodo('div', 'quien', il, r.iluo.persona + ': de ' + r.iluo.de + ' a ' + r.iluo.a);
          const fila = nodo('div', 'fila', il);
          const nombres = { I: 'En formación', L: 'Con apoyo', U: 'Autónomo', O: 'Forma a otros' };
          for (const n of ['I', 'L', 'U', 'O']) nodo('div', 'nivel' + (n === r.iluo.de ? ' de' : '') + (n === r.iluo.a ? ' a' : ''), fila, '<b>' + n + '</b><span>' + nombres[n] + '</span>');
          resPartes.push(il);
        }
        const bs = nodo('div', 'res-bases', res);
        nodo('span', 'etq', bs, 'BASES QUE CUBRE');
        resPartes.push(bs.firstChild);
        for (const b of r.bases) { const ch = nodo('span', '', bs, chipBase(b)).firstChild; resPartes.push(ch); }
      }
      const llamadas = (p.llamadas || []).map((l) => ({ l, e: nodo('div', 'llamada', caja, l.texto) }));
      // Tapas: van dentro de la cámara (en coordenadas de la grabación), así siguen al zoom y al desplazamiento.
      const tapas = (p.tapas || []).map((tp) => ({ tp, e: nodo('div', 'tapa', camara, tp.texto) }));
      return function (lt) {
        // Entrada del marco.
        let mx = 0, mo = 1, my = 0;
        if (p.entrada === 'empuje') {
          const a = k(lt, 0, 0.5, 'entrada');
          mx = 115 * (1 - a); mo = lim(a / 0.6);
          if (previo) { mostrar(previo, a < 1); T(previo, 1 - a, -115 * a, 0); }
        } else if (p.entrada === 'aparece') {
          const a = k(lt, 0, 0.5, 'entrada'); my = 40 * (1 - a); mo = lim(a / 0.6);
          if (previo) mostrar(previo, false);
        } else if (previo) mostrar(previo, false);
        // Resultado: el marco se encoge a la izquierda y entra el panel.
        let rk = 0;
        if (res) {
          const r0 = p.resultado.ini - 0.15;
          rk = k(lt, r0, 0.7, 'camara');
          mostrar(res, lt >= r0 + 0.4);
          const pa = k(lt, r0 + 0.45, 0.45, 'entrada');
          T(res, lim(pa / 0.6), 40 * (1 - pa), 0);
          resPartes.forEach((e2, i) => { const a = k(lt, r0 + 0.55 + i * 0.07, 0.45, 'entrada'); T(e2, lim(a / 0.6), 0, 16 * (1 - a)); });
        }
        const sx = mezcla(1, 0.735, rk), ox = mezcla(0, 120 - 180, rk), oy = mezcla(0, 168 - 76, rk);
        marco.style.opacity = mo;
        marco.style.transform = 'translate(' + (mx + ox).toFixed(2) + 'px,' + (my + oy).toFixed(2) + 'px) scale(' + sx.toFixed(5) + ')';
        const cam = camaraEn(p.camara, lt);
        const ap = aplicarCamara(camara, cam, 1560, 878, 0.8125);
        // Tapas fijas, del mismo tamaño siempre: una antes del desplazamiento de la página y otra después. Mientras la
        // página se mueve no hay etiqueta: la franja va pixelada en el propio vídeo (hyperframes.py, tramos_tapas).
        for (const { tp, e } of tapas) {
          const q = tp.tramos.find((r) => lt >= r[0] && lt < r[1]);
          if (!q) { e.style.opacity = 0; continue; }
          const fi = q[0] > 0.01 ? k(lt, q[0], 0.06, 'lineal') : 1, fo = q[1] < p.dur - 0.01 ? k(lt, q[1] - 0.06, 0.06, 'lineal') : 0;
          e.style.opacity = Math.min(fi, 1 - fo);
          e.style.left = q[2] + 'px'; e.style.top = q[3] + 'px'; e.style.width = q[4] + 'px'; e.style.height = q[5] + 'px';
        }
        // Llamadas: etiqueta junto a una caja de la grabación, siguiendo a la cámara.
        for (const { l, e } of llamadas) {
          const v = vida(lt, l.ini, l.fin, 0.45, 0.3);
          mostrar(e, lt >= l.ini && lt <= l.fin + 0.3);
          if (lt < l.ini || lt > l.fin + 0.3) continue;
          // A la derecha de la caja (en pantalla, con la cámara y el marco de ahora); si no cabe, a la izquierda.
          const izq = 180 + ox + sx * (ap.tx + ap.s * l.caja[0]);
          const der = 180 + ox + sx * (ap.tx + ap.s * (l.caja[0] + l.caja[2]));
          const arriba = 76 + oy + sx * (ap.ty + ap.s * l.caja[1]);
          const centro = 76 + oy + sx * (ap.ty + ap.s * (l.caja[1] + l.caja[3] / 2));
          const ancho = e.offsetWidth || 300;
          let X = der + 18, Y = centro - 26;
          if (X + ancho > 1740) X = izq - ancho - 18;
          if (X < 180) { X = Math.max(180, Math.min(1740 - ancho, izq)); Y = arriba - 66; }
          if (Y > 880) Y = arriba - 66;
          e.style.left = X.toFixed(1) + 'px';
          e.style.top = Math.max(80, Y).toFixed(1) + 'px';
          e.style.opacity = v.o;
          e.style.transform = 'translateX(' + (-14 * (1 - v.a)).toFixed(1) + 'px)';
        }
      };
    },

    funcionalidad(p, caja) {
      const raya = nodo('div', 'raya-funcs', caja);
      const rs = p.raya.map((s) => { const e = nodo('div', 's ' + s.estado, raya); e.style.left = s.x + 'px'; e.style.width = s.w + 'px'; return e; });
      const col = nodo('div', '', caja); col.style.cssText = 'position:absolute;left:120px;top:' + p.y0 + 'px;width:800px;';
      const etq = nodo('div', 'etiqueta', col);
      const tit = nodo('div', 't-titular', col); tit.style.cssText = 'margin-top:22px;font-size:64px;line-height:72px;';
      const lineas = lineasMascara(tit, p.titulo_lineas);
      const pq = nodo('div', '', col); pq.style.marginTop = '34px';
      nodo('div', 't-sub', pq, 'Para qué sirve');
      const pqt = nodo('div', 't-texto', pq, p.para_que); pqt.style.marginTop = '10px';
      // Avatares apilados: se solapan un 20 % como mucho y llevan un aro que los separa del fondo y entre sí.
      const avs = p.persona.avatares.map((q, i) => avatar(q, 'margin-left:' + (i ? -6 : 0) + 'px;box-shadow:0 0 0 2px #2B3036,inset 0 0 0 2px rgba(255,255,255,.22)')).join('');
      const per = nodo('div', '', col, '<div class="persona"><span class="pila">' + avs + '</span><b>' + p.persona.texto + '</b></div>');
      per.style.cssText = 'margin-top:30px;display:flex;';
      const bs = nodo('div', '', col); bs.style.cssText = 'margin-top:16px;display:flex;flex-wrap:wrap;gap:10px;';
      const chips = p.bases.map((b) => nodo('span', '', bs, chipBase(b)).firstChild);
      const pv = caja.querySelector('.preview');
      const lienzo = pv.querySelector('.lienzo');
      const primera = pv.querySelector('img.primera');
      // Sin línea de RESULTADO bajo la vista previa: el resultado va en el panel del final de la demostración.
      lienzo.style.transform = 'scale(0.8125)';
      const d = p.dur;
      return function (lt) {
        // Todo el texto está en pantalla hacia 1,1 s y se queda hasta 0,72 s antes del final (hyperframes.py calcula la
        // duración con palabras / 3 + 1 s del «para qué sirve»).
        const sal = d - 0.72;
        rs.forEach((e, i) => { const a = k(lt, i * (1 / 40), 0.2, 'micro'); e.style.transform = 'scaleX(' + a.toFixed(3) + ')'; e.style.transformOrigin = '0 50%'; e.style.opacity = 1 - k(lt, sal, 0.3, 'salida'); });
        letraALetra(etq, p.etiqueta, lt, 0.06);
        const vs = vida(lt, 0.06, sal, 0.2, 0.3);
        etq.style.opacity = vs.o;
        revelarLineas(lineas, lt, 0.12, 0.08);
        tit.style.opacity = 1 - k(lt, sal, 0.3, 'salida');
        const v2 = vida(lt, 0.4, sal + 0.04, 0.45, 0.3); T(pq, v2.o, 0, 24 * (1 - v2.a) - 10 * v2.b);
        const v3 = vida(lt, 0.6, sal + 0.08, 0.45, 0.3); T(per, v3.o, 0, 12 * (1 - v3.a));
        chips.forEach((c, i) => { const v = vida(lt, 0.66 + i * 0.05, sal + 0.1, 0.2, 0.3); T(c, v.o, 0, 0, mezcla(0.96, 1, v.a)); });
        // Vista previa: entra desde la derecha; al final crece hasta el marco (zoom a través).
        const a = k(lt, 0.15, 0.45, 'entrada');
        const z = k(lt, d - 0.7, 0.7, 'camara');
        const s0 = p.pv.w / 1560;
        const x = mezcla(p.pv.x + 115 * (1 - a), 180, z), y = mezcla(p.pv.y, 76, z), s = mezcla(s0, 1, z);
        pv.style.opacity = lim(a / 0.6);
        pv.style.transform = 'translate(' + x.toFixed(2) + 'px,' + y.toFixed(2) + 'px) scale(' + s.toFixed(5) + ')';
        primera.style.opacity = k(lt, d - 0.7, 0.25, 'lineal');
      };
    },

    mapa(p, caja) {
      const cabz = nodo('div', '', caja); cabz.style.cssText = 'position:absolute;left:180px;top:' + p.y_cab + 'px;width:1560px;';
      const etq = nodo('div', 'etiqueta', cabz);
      const tit = nodo('div', 't-titular', cabz); tit.style.cssText = 'margin-top:14px;font-size:' + p.tam_titulo + 'px;line-height:' + Math.round(p.tam_titulo * 1.14) + 'px;';
      const lineas = lineasMascara(tit, p.titulo_lineas);
      let sub = null, pat = [];
      if (p.subtitulo) {
        const caja2 = nodo('div', '', cabz); caja2.style.cssText = 'position:relative;margin-top:14px;';
        sub = nodo('div', '', caja2, p.subtitulo); sub.style.cssText = 'font-size:26px;line-height:34px;color:#AEB5BF;max-width:1400px;';
        if (p.patron) {
          const fila = nodo('div', '', caja2); fila.style.cssText = 'position:absolute;left:0;top:0;display:flex;gap:14px;align-items:center;';
          pat = p.patron.map((x, i) => {
            const e = nodo('span', '', fila, (i ? '<span style="color:#F2C200;margin-right:14px">' + svgIcono('arrow-right', 'style="width:22px;height:22px;vertical-align:-4px"') + '</span>' : '') +
              '<span class="chip" style="font-family:JetBrains Mono,monospace;font-weight:600;letter-spacing:.04em;text-transform:uppercase;font-size:20px;padding:0 16px"><b style="color:#F2C200;margin-right:8px">' + (i + 1) + '</b>' + x.texto + '</span>');
            return { x, e };
          });
        }
      }
      const tes = p.teselas.map((s) => {
        const e = nodo('div', 'tesela ' + s.estado, caja);
        e.style.cssText += 'left:' + s.x + 'px;top:' + s.y + 'px;width:' + s.w + 'px;height:' + s.h + 'px;';
        e.innerHTML = '<div class="cab"><span class="num">' + s.num + '</span><span class="ico">' + svgIcono(s.icono) + '</span></div>' +
          '<div class="verbo">' + s.verbo + '</div><div class="tit">' + s.titulo + '</div>' +
          '<ul>' + s.funcs.map((f) => '<li><b>' + f[0] + '</b>' + f[1] + '</li>').join('') + '</ul>' + (s.ciclo ? '<span class="ciclo">CICLO</span>' : '');
        const marca = nodo('div', '', e); marca.style.cssText = 'position:absolute;inset:0;border-radius:18px;box-shadow:inset 0 0 0 3px #F2C200;opacity:0;';
        return { s, e, marca };
      });
      const flechas = (p.flechas || []).map((f) => { const e = nodo('div', '', caja, svgIcono('arrow-right', 'class="flecha"')); e.style.cssText = 'position:absolute;left:' + f.x + 'px;top:' + f.y + 'px;color:#F2C200;'; return e; });
      const d = p.dur;
      return function (lt) {
        // La salida termina justo al acabar: la tarjeta siguiente empieza a revelarse en su primer fotograma, sin un
        // rato de fondo vacío entre las dos (revisión del 11/10).
        const sal = d - 0.3;
        const fueraTodo = p.salida === 'texto';
        letraALetra(etq, p.etiqueta, lt, 0.2);
        etq.style.opacity = vida(lt, 0.2, sal, 0.2, 0.3).o;
        revelarLineas(lineas, lt, 0.3, 0.09);
        tit.style.opacity = 1 - k(lt, sal, 0.3, 'salida');
        if (sub) {
          const fueraSub = pat.length ? pat[0].x.t - 0.25 : sal;
          const v = vida(lt, 0.6, Math.min(fueraSub, sal), 0.45, 0.3); T(sub, v.o, 0, 24 * (1 - v.a));
          pat.forEach(({ x, e }) => { const w = vida(lt, x.t, sal, 0.45, 0.3); T(e, w.o, 0, 16 * (1 - w.a)); });
        }
        tes.forEach(({ s, e, marca }, i) => {
          let o = 1, y = 0, sc = 1;
          if (s.aparece != null) {
            const v = k(lt, 0.5 + i * 0.06, 0.45, 'entrada');
            const on = k(lt, s.aparece, 0.3, 'entrada');
            o = lim(v / 0.6) * mezcla(0.35, 1, on); y = 30 * (1 - v); sc = mezcla(0.97, 1, on);
          }
          if (fueraTodo) { const b = k(lt, sal - 0.06 + i * 0.01, 0.28, 'salida'); o = Math.min(o, 1 - b); y -= 14 * b; }
          if (s.estado === 'actual') {
            const h = k(lt, 0.25, 0.45, 'entrada');
            marca.style.opacity = h;
            sc *= mezcla(1, 1.03, h);
          }
          T(e, o, 0, y, sc);
        });
        flechas.forEach((f) => { f.style.opacity = (p.flechas_aparecen != null ? k(lt, p.flechas_aparecen, 0.45) : 1) * (fueraTodo ? 1 - k(lt, sal, 0.3, 'salida') : 1); });
      };
    },

    portada(p, caja) {
      const marca = nodo('div', 'logo', caja, LOGO(64)); marca.style.cssText = 'position:absolute;left:120px;top:92px;';
      const pal = nodo('div', '', caja, 'CidIA'); pal.style.cssText = 'position:absolute;left:202px;top:96px;font-weight:700;font-size:46px;line-height:56px;';
      const arco = marca.querySelector('.lg-arco'), punto = marca.querySelector('.lg-punto');
      arco.setAttribute('stroke-dasharray', '46'); arco.setAttribute('stroke-dashoffset', '46');
      const col = nodo('div', '', caja); col.style.cssText = 'position:absolute;left:120px;top:' + p.y0 + 'px;width:860px;';
      const etq = nodo('div', 'etiqueta', col);
      const tit = nodo('div', 't-titular', col); tit.style.cssText = 'margin-top:26px;font-size:88px;line-height:96px;font-stretch:104%;';
      const lineas = lineasMascara(tit, p.titulo_lineas);
      lineas[lineas.length - 1].style.color = '#F2C200';
      const sub = nodo('div', '', col, p.subtitulo); sub.style.cssText = 'margin-top:30px;font-size:32px;line-height:44px;color:#D5D9DF;max-width:760px;';
      const eq = nodo('div', 't-sub', caja, p.equipo); eq.style.cssText += 'position:absolute;left:120px;top:880px;';
      const capt = Array.from(caja.querySelectorAll('.captura'));
      const d = p.dur;
      return function (lt) {
        const sal = d - 0.4;
        const out = (t0) => k(lt, sal + t0, 0.3, 'salida');
        const a = k(lt, 0, 0.45, 'entrada');
        T(marca, lim(a / 0.6) * (1 - out(0)), 0, 0, mezcla(0.9, 1, a));
        arco.setAttribute('stroke-dashoffset', (46 * (1 - k(lt, 0.1, 0.6, 'entrada'))).toFixed(2));
        punto.style.opacity = k(lt, 0.6, 0.2, 'micro');
        const ap = k(lt, 0.55, 0.45, 'entrada'); T(pal, lim(ap / 0.6) * (1 - out(0)), -12 * (1 - ap), 0);
        letraALetra(etq, p.etiqueta, lt, 0.4);
        etq.style.opacity = 1 - out(0.02);
        revelarLineas(lineas, lt, 0.55, 0.09);
        tit.style.opacity = 1 - out(0.04);
        const v = vida(lt, 1.1, sal + 0.06, 0.45, 0.3); T(sub, v.o, 0, 24 * (1 - v.a));
        const v2 = vida(lt, 1.4, sal + 0.08, 0.45, 0.3); T(eq, v2.o, 0, 12 * (1 - v2.a));
        capt.forEach((c, i) => {
          const e = k(lt, 0.2 + i * 0.14, 0.7, 'entrada');
          const deriva = -0.02 * 1560 * lim((lt - 1) / 8) * (1 + i * 0.4);
          const sx = k(lt, sal + (2 - i) * 0.04, 0.3, 'salida');
          T(c, lim(e / 0.5) * (1 - sx), (1 - e) * (260 + 120 * i) + deriva + 200 * sx, 0, 1);
        });
      };
    },

    problema(p, caja) {
      const col = nodo('div', '', caja); col.style.cssText = 'position:absolute;left:180px;top:170px;width:1560px;';
      const etq = nodo('div', 'etiqueta', col);
      const tit = nodo('div', 't-titular', col); tit.style.cssText = 'margin-top:20px;font-size:72px;line-height:82px;';
      const lineas = lineasMascara(tit, p.titulo_lineas);
      const filas = p.cifras.map((c, i) => {
        const f = nodo('div', '', caja); f.style.cssText = 'position:absolute;left:180px;top:' + (420 + i * 190) + 'px;width:1560px;height:160px;';
        const num = nodo('div', 'mono', f); num.style.cssText = 'position:absolute;left:0;top:0;font-size:104px;line-height:120px;font-weight:700;color:' + c.color + ';';
        const txt = nodo('div', '', f, c.texto); txt.style.cssText = 'position:absolute;left:400px;top:18px;font-size:34px;line-height:42px;color:#F5F6F8;font-weight:600;';
        const bar = nodo('div', '', f); bar.style.cssText = 'position:absolute;left:400px;top:84px;height:18px;border-radius:8px;background:' + c.color + ';width:' + c.ancho + 'px;transform-origin:0 50%;';
        return { c, f, num, txt, bar };
      });
      const fuente = nodo('div', 't-sub', caja, p.fuente); fuente.style.cssText += 'position:absolute;left:180px;top:850px;text-transform:none;letter-spacing:.02em;font-weight:500;';
      const d = p.dur;
      return function (lt) {
        const sal = d - 0.4;
        letraALetra(etq, p.etiqueta, lt, 0.15);
        etq.style.opacity = 1 - k(lt, sal, 0.3, 'salida');
        revelarLineas(lineas, lt, 0.25, 0.09);
        tit.style.opacity = 1 - k(lt, sal, 0.3, 'salida');
        filas.forEach((r, i) => {
          // La fila entra pronto, apagada y a cero; cuenta y crece cuando la voz dice la cifra.
          const t0 = r.c.t != null ? r.c.t : 0.8 + i * 0.6;
          const v = vida(lt, 0.8 + i * 0.15, sal + 0.04 * i, 0.45, 0.3);
          const on = k(lt, t0, 0.3, 'entrada');
          T(r.f, v.o * mezcla(0.45, 1, on), 0, 24 * (1 - v.a));
          const n = r.c.valor * k(lt, t0, 1.2, 'entrada');
          r.num.textContent = n.toFixed(1).replace('.', ',') + ' M';
          r.num.style.opacity = on;
          r.bar.style.transform = 'scaleX(' + Math.max(0.02, k(lt, t0 + 0.2, 0.9, 'entrada')).toFixed(3) + ')';
        });
        const v = vida(lt, 2.2, sal, 0.45, 0.3); T(fuente, v.o, 0, 12 * (1 - v.a));
      };
    },

    reparto(p, caja) {
      const col = nodo('div', '', caja); col.style.cssText = 'position:absolute;left:180px;top:120px;width:1560px;';
      const etq = nodo('div', 'etiqueta', col);
      const tit = nodo('div', 't-titular', col); tit.style.cssText = 'margin-top:16px;font-size:60px;line-height:68px;';
      const lineas = lineasMascara(tit, p.titulo_lineas);
      const fichas = p.personas.map((q, i) => {
        const e = nodo('div', 'ficha', caja, avatar(q) + '<div><b>' + q.nombre + '</b><span>' + q.papel + '</span><small>' + q.departamento + '</small></div>');
        e.style.left = (180 + (i % 3) * 540) + 'px'; e.style.top = (300 + Math.floor(i / 3) * 172) + 'px';
        const ani = nodo('div', '', e); ani.style.cssText = 'position:absolute;inset:0;border-radius:18px;box-shadow:inset 0 0 0 3px #F2C200;opacity:0;';
        return { q, e, ani };
      });
      const d = p.dur;
      return function (lt) {
        const sal = d - 0.36;
        letraALetra(etq, p.etiqueta, lt, 0.12);
        etq.style.opacity = 1 - k(lt, sal, 0.3, 'salida');
        revelarLineas(lineas, lt, 0.2, 0.09);
        tit.style.opacity = 1 - k(lt, sal, 0.3, 'salida');
        fichas.forEach(({ q, e, ani }, i) => {
          const v = vida(lt, 0.4 + i * 0.07, sal + i * 0.015, 0.45, 0.3);
          T(e, v.o, 0, 30 * (1 - v.a));
          ani.style.opacity = q.nombrada != null ? k(lt, q.nombrada, 0.2, 'micro') : 0;
        });
      };
    },

    criterios(p, caja) {
      // Filas compactas a la izquierda (peso, criterio y miniatura de su prueba) y, a la derecha, el criterio que nombra
      // la voz en grande: su texto y su prueba, que crece desde la miniatura de la fila, se reproduce 3 s y vuelve a ella.
      const col = nodo('div', '', caja); col.style.cssText = 'position:absolute;left:120px;top:72px;width:1700px;';
      const etq = nodo('div', 'etiqueta', col);
      const tit = nodo('div', 't-titular', col); tit.style.cssText = 'margin-top:12px;font-size:54px;line-height:62px;font-stretch:104%;';
      const lineas = lineasMascara(tit, p.titulo_lineas);
      const FILA = { x: 120, w: 820, h: 100, y0: 236, paso: 116 };
      const MEDIA = { x: 1000, y: 430, w: 800, h: 450 };
      const filas = p.criterios.map((c, i) => {
        const mini = c.img ? '<img src="' + c.img + '">' : '<span class="mini-tablero">' + '<i></i>'.repeat(18) + '</span>';
        const e = nodo('div', 'criterio', caja,
          '<div class="peso"><b>' + c.peso + '<small>%</small></b><i style="width:' + Math.round(110 * c.peso / 40) + 'px"></i></div>' +
          '<div class="txt"><b>' + c.nombre + '</b></div><div class="mini">' + mini + '</div>');
        e.style.left = FILA.x + 'px'; e.style.top = (FILA.y0 + i * FILA.paso) + 'px'; e.style.width = FILA.w + 'px'; e.style.height = FILA.h + 'px';
        const pan = nodo('div', 'crit-panel', caja, '<b>' + c.nombre + '</b><span>' + c.texto + '</span>');
        return { c, e, pan, bar: e.querySelector('.peso i'), cm: c.clip ? caja.querySelector('#cm-' + i) : null };
      });
      const media = caja.querySelector('.crit-media');
      media.style.cssText = 'left:' + MEDIA.x + 'px;top:' + MEDIA.y + 'px;width:' + MEDIA.w + 'px;height:' + MEDIA.h + 'px;';
      const tab = nodo('div', 'tablero', media, '<div class="tt">' + p.cobertura.titulo + '</div><div class="ts">' + p.cobertura.sub + '</div>');
      const cel = nodo('div', 'celdas', tab);
      const celdas = p.cobertura.celdas.map((c) => nodo('div', 'celda', cel, c === 'ok' ? CHECK_GRANDE : MEDIO.replace('class="medio"', '')));
      nodo('div', 'leyenda', tab, '<span>' + CHECK + ' demostrado</span><span>' + MEDIO + ' simplificado o preparado</span>');
      const d = p.dur;
      // Rectángulo de la miniatura de una fila (en pantalla), para que la prueba crezca desde ella y vuelva a ella.
      const rectMini = (i) => ({ x: FILA.x + FILA.w - 18 - 150, y: FILA.y0 + i * FILA.paso + 8, w: 150, h: 84 });
      return function (lt) {
        letraALetra(etq, p.etiqueta, lt, 0.2);
        revelarLineas(lineas, lt, 0.3, 0.09);
        let activa = -1;
        filas.forEach(({ c }, i) => { if (lt >= c.t) activa = i; });
        filas.forEach(({ c, e, pan, bar }, i) => {
          // Las cinco filas entran pronto, al 60 %; cada una se enciende cuando la voz la nombra.
          const v = vida(lt, 0.6 + i * 0.08, null, 0.45);
          const on = i === activa ? k(lt, c.t, 0.3, 'entrada') : 0;
          T(e, v.o * mezcla(0.6, 1, on), -40 * (1 - v.a), 0);
          bar.style.transform = 'scaleX(' + k(lt, c.t + 0.1, 0.45, 'entrada').toFixed(3) + ')';
          bar.style.transformOrigin = '0 50%';
          e.classList.toggle('vivo', i === activa);
          const pv = vida(lt, c.t + 0.1, c.fin - 0.35, 0.4, 0.3);
          mostrar(pan, pv.o > 0.001);
          T(pan, pv.o, 0, 18 * (1 - pv.a));
        });
        // La prueba del criterio activo: crece desde su miniatura, se queda y vuelve a ella antes del siguiente.
        if (activa < 0) { media.style.opacity = 0; return; }
        const f = filas[activa];
        const crece = k(lt, f.c.t + 0.05, 0.45, 'camara');
        const vuelve = activa + 1 < filas.length ? k(lt, f.c.fin - 0.42, 0.4, 'camara') : 0;
        const z = crece * (1 - vuelve);
        const r = rectMini(activa);
        const s = mezcla(r.w / MEDIA.w, 1, z);
        const x = mezcla(r.x, MEDIA.x, z) - MEDIA.x, y = mezcla(r.y, MEDIA.y, z) - MEDIA.y;
        media.style.opacity = lim(Math.min(crece, 1 - vuelve) * 4);
        media.style.transform = 'translate(' + x.toFixed(1) + 'px,' + y.toFixed(1) + 'px) scale(' + s.toFixed(4) + ')';
        mostrar(tab, activa === 0);
        filas.forEach(({ c, cm }, i) => {
          if (!cm) return;
          mostrar(cm, i === activa);
          if (i !== activa) return;
          const enClip = lt >= c.clip.ini && lt < c.clip.ini + c.clip.dur;
          const ia = cm.querySelector('img.a'), vd = cm.querySelector('video'), ib = cm.querySelector('img.b');
          if (ia) ia.style.opacity = lt < c.clip.ini ? 1 : 0;
          if (vd) vd.style.opacity = enClip ? 1 : 0;
          if (ib) ib.style.opacity = lt >= c.clip.ini + c.clip.dur ? 1 : 0;
        });
        if (activa === 0) {
          const t0 = p.cobertura.t;
          celdas.forEach((c, i) => {
            const a = k(lt, t0 + 0.3 + i / 30 * 2, 0.2, 'micro');
            const s2 = c.firstChild;
            if (s2) { s2.style.opacity = lim(a / 0.6); s2.style.transform = 'scale(' + mezcla(0.5, 1, a).toFixed(3) + ')'; }
          });
        }
      };
    },

    implantacion(p, caja) {
      // Composición centrada: título, los dos instaladores lado a lado, la cifra grande y las licencias.
      const col = nodo('div', '', caja); col.style.cssText = 'position:absolute;left:0;top:96px;width:1920px;text-align:center;';
      const etq = nodo('div', 'etiqueta', col);
      const tit = nodo('div', 't-titular', col); tit.style.cssText = 'margin-top:16px;font-size:58px;line-height:66px;font-stretch:104%;';
      const lineas = lineasMascara(tit, p.titulo_lineas);
      const tarjetas = p.tarjetas.map((c, i) => {
        const e = nodo('div', 'instala', caja, '<span class="ico">' + svgIcono(c.icono) + '</span><div><b>' + c.nombre + '</b><span>' + c.texto + '</span></div>');
        e.style.left = (240 + i * 740) + 'px'; e.style.top = '290px';
        return { c, e };
      });
      const coste = nodo('div', 'coste', caja, '<span class="gran">' + p.coste.gran + '</span><span class="txt">' + p.coste.texto + '</span>');
      const lic = nodo('div', '', caja, p.licencias); lic.style.cssText = 'position:absolute;left:0;top:790px;width:1920px;text-align:center;font-size:28px;line-height:38px;color:#D5D9DF;';
      const d = p.dur;
      return function (lt) {
        const sal = d - 0.4;
        letraALetra(etq, p.etiqueta, lt, 0.15);
        etq.style.opacity = 1 - k(lt, sal, 0.3, 'salida');
        revelarLineas(lineas, lt, 0.25, 0.09);
        tit.style.opacity = 1 - k(lt, sal, 0.3, 'salida');
        tarjetas.forEach(({ c, e }, i) => { const v = vida(lt, c.t, sal + i * 0.03, 0.45, 0.3); T(e, v.o, 0, 40 * (1 - v.a)); });
        const vc = vida(lt, p.coste.t, sal, 0.45, 0.3); T(coste, vc.o, 0, 0, mezcla(0.94, 1, vc.a));
        const v = vida(lt, p.t_licencias, sal, 0.45, 0.3); T(lic, v.o, 0, 24 * (1 - v.a));
      };
    },

    final(p, caja) {
      const verbos = nodo('div', '', caja); verbos.style.cssText = 'position:absolute;left:0;top:96px;width:1920px;text-align:center;font-family:Archivo;font-weight:800;font-size:44px;line-height:52px;';
      const vs = p.recap.map((r, i) => nodo('span', '', verbos, (i ? '<span style="color:#3A4048"> · </span>' : '') + r.verbo));
      const recs = Array.from(caja.querySelectorAll('.recap'));
      const lock = nodo('div', '', caja); lock.style.cssText = 'position:absolute;left:0;top:250px;width:1920px;text-align:center;';
      lock.innerHTML = '<div style="display:inline-flex;align-items:center;gap:30px">' + LOGO(132) + '<span style="font-weight:700;font-size:118px;line-height:132px">CidIA</span></div>';
      const lema = nodo('div', 't-titular', caja, p.lema); lema.style.cssText += 'position:absolute;left:0;top:452px;width:1920px;text-align:center;font-size:64px;line-height:72px;';
      const claves = nodo('div', 'etiqueta', caja, p.claves); claves.style.cssText += 'position:absolute;left:0;top:560px;width:1920px;text-align:center;font-size:22px;';
      const eq = nodo('div', '', caja, p.equipo); eq.style.cssText = 'position:absolute;left:0;top:640px;width:1920px;text-align:center;font-size:30px;line-height:40px;color:#AEB5BF;';
      const con = nodo('div', 't-sub', caja, p.convocatoria); con.style.cssText += 'position:absolute;left:0;top:704px;width:1920px;text-align:center;';
      // Notas de veracidad encima de la franja de subtítulos (antes la placa tapaba la tercera línea).
      const cre = nodo('div', 'creditos', caja, p.creditos.join('<br>')); cre.style.top = '772px';
      const arco = lock.querySelector('.lg-arco'), punto = lock.querySelector('.lg-punto');
      arco.setAttribute('stroke-dasharray', '46');
      const d = p.dur, tL = p.t_lockup;
      return function (lt) {
        // Recapitulación: cada verbo enciende su captura.
        const fueraR = k(lt, tL - 0.4, 0.3, 'salida');
        verbos.style.opacity = vida(lt, 0.1, tL - 0.4, 0.45, 0.3).o;
        vs.forEach((v, i) => { const on = k(lt, 0.25 + i * p.paso, 0.2, 'micro'); v.style.color = on > 0.5 ? '#F5F6F8' : '#5A6270'; });
        recs.forEach((r, i) => {
          const a = k(lt, 0.15 + i * 0.06, 0.45, 'entrada');
          const on = k(lt, 0.25 + i * p.paso, 0.2, 'micro');
          T(r, lim(a / 0.6) * mezcla(0.35, 1, on) * (1 - fueraR), 0, 30 * (1 - a), mezcla(0.97, 1, on) * mezcla(1, 0.94, fueraR));
        });
        // Cierre con la marca.
        const a = k(lt, tL, 0.45, 'entrada');
        T(lock, lim(a / 0.6), 0, 0, mezcla(0.9, 1, a));
        arco.setAttribute('stroke-dashoffset', (46 * (1 - k(lt, tL + 0.1, 0.6, 'entrada'))).toFixed(2));
        punto.style.opacity = k(lt, tL + 0.6, 0.2, 'micro');
        const l2 = k(lt, tL + 0.5, 0.45, 'entrada'); T(lema, lim(l2 / 0.6), 0, 24 * (1 - l2));
        const l3 = k(lt, tL + 0.8, 0.45, 'entrada'); T(claves, lim(l3 / 0.6), 0, 16 * (1 - l3));
        const l4 = k(lt, tL + 1.0, 0.45, 'entrada'); T(eq, lim(l4 / 0.6), 0, 16 * (1 - l4));
        const l5 = k(lt, tL + 1.15, 0.45, 'entrada'); T(con, lim(l5 / 0.6), 0, 16 * (1 - l5));
        const l6 = k(lt, tL + 1.4, 0.45, 'entrada'); T(cre, lim(l6 / 0.6), 0, 12 * (1 - l6));
      };
    },

    apertura(p, caja) {
      const clips = Array.from(caja.querySelectorAll('.marco')).map((m, i) => ({ m, cam: m.querySelector('.camara'), c: p.clips[i] }));
      const frases = p.clips.map((c) => { const f = nodo('div', 'frase-ap', caja); const s = lineasMascara(f, [c.frase]); return { f, s }; });
      return function (lt) {
        clips.forEach(({ m, cam, c }, i) => {
          const si = lt >= c.ini && lt < c.ini + c.dur;
          mostrar(m, si);
          const fr = frases[i];
          mostrar(fr.f, si);
          if (!si) return;
          const u = lt - c.ini;
          const z = mezcla(c.z0, c.z1, lim(u / c.dur));
          aplicarCamara(cam, { cx: c.cx, cy: c.cy, z }, 1560, 878, 0.8125);
          revelarLineas(fr.s, u, 0.12, 0.09);
        });
      };
    },
  };

  // ------------------------------------------------------------------ piezas
  for (const p of D.piezas) {
    let caja = document.getElementById('p-' + p.id);
    if (!caja) caja = nodo('div', 'pieza', RAIZ);
    caja.classList.add('pieza');
    const f = CONSTRUCTORES[p.tipo];
    const pintarPieza = f ? f(p, caja) : () => {};
    mostrar(caja, false);
    PIEZAS.push({ p, caja, pintar: pintarPieza });
  }
  // Las capas globales, por encima de las piezas.
  [cab, reloj, subsCapa, rail, pieIzq, pieDer, cortina, negro].forEach((e) => RAIZ.appendChild(e));

  // ------------------------------------------------------------------ reloj de HyperFrames
  const proxy = { _t: -1 };
  Object.defineProperty(proxy, 't', { get() { return this._t; }, set(v) { this._t = v; pintar(v); } });
  pintar(0);
  const tl = gsap.timeline({ paused: true });
  tl.fromTo(proxy, { t: 0 }, { t: D.duracion, duration: D.duracion, ease: 'none' }, 0);
  window.__cidiaTimeline = tl;
  // Depuración: index.html#t=12.5 pinta ese instante al abrirlo en un navegador cualquiera (sin HyperFrames).
  const m = /[#&]t=([0-9.]+)/.exec(location.hash || '');
  if (m) { const tt = parseFloat(m[1]); setTimeout(() => { tl.seek(tt); pintar(tt); }, 300); }   // el index.html lo registra en window.__timelines con el id de su composición
  window.__pintarCidia = pintar;
})();
