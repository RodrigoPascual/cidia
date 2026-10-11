"""Música y efectos del vídeo v2 de CidIA, sintetizados aquí mismo (sin muestras ni grabaciones de terceros).

La música sigue la guía de estilo (04_VIDEO/v2/notas/guia-estilo.md, apartado 13): instrumental a 96 pulsaciones
por minuto en re dórico, con colchón cálido con armónicos, pulso de sintetizador suave, piano con ataque y bajo discreto;
en los bloques, solo un charles o un shaker muy suaves; bombo y caja en la apertura, las bases y el cierre. Paso alto a
80 Hz para no enturbiar la voz. Cada sección (apertura, bloques con dos variantes que se alternan, bases y cierre)
tiene su energía y empieza en un tiempo fuerte, así que los cambios de bloque caen en la parte.

Los efectos (clic, soplo, confirmación, pitido del micrófono y golpe de la portada) también se generan aquí.

Todo es determinista (semillas fijas): el mismo guion da el mismo audio. Sin licencias de terceros que cumplir.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

TASA = 48000
BPM = 96.0
TIEMPO = 60.0 / BPM          # 0,625 s
COMPAS = 4 * TIEMPO          # 2,5 s

# Acordes en re dórico (MIDI): bajo y voces del colchón.
ACORDES = {
    'Dm9': (38, (50, 53, 57, 60, 64)),
    'G9': (43, (55, 59, 62, 65, 69)),
    'Fmaj9': (41, (53, 57, 60, 64, 67)),
    'Cmaj9': (36, (52, 55, 59, 62, 67)),
    'Am7': (45, (52, 55, 60, 64, 69)),
    'Em7': (40, (52, 55, 59, 62, 67)),
    'Dfin': (38, (50, 57, 62, 64, 65)),   # re menor con novena, abierto: la resolución final
}
PROGRESIONES = {
    # Dos compases por acorde: 8 compases = 20 s.
    'a': ['Dm9', 'Dm9', 'G9', 'G9', 'Fmaj9', 'Fmaj9', 'Cmaj9', 'Cmaj9'],
    'b': ['Dm9', 'Dm9', 'Am7', 'Am7', 'Fmaj9', 'Fmaj9', 'G9', 'G9'],
    'c': ['Dm9', 'G9', 'Fmaj9', 'Cmaj9', 'Dm9', 'G9', 'Am7', 'Cmaj9'],
}
# Energía de cada tipo de sección: ganancia de cada capa (colchón, pulso, piano, bajo, bombo, charles, caja, shaker).
# Revisión del 11/10: la versión anterior casi no tenía nada por encima de 500 Hz y los bloques iban sin percusión
# («colchón de órgano apagado»). Ahora el colchón y el piano tienen armónicos y ataque, los bloques llevan un charles y
# un shaker muy suaves a 96 ppm y las dos variantes se distinguen (patrón del pulso, registro del piano y percusión).
ENERGIA = {
    'apertura': dict(pad=0.9, pulso=0.85, piano=0.6, bajo=1.0, bombo=0.9, charles=0.55, caja=0.0, shaker=0.35, prog='c', semicorcheas=True),
    'portada': dict(pad=1.0, pulso=0.8, piano=0.75, bajo=1.0, bombo=0.75, charles=0.5, caja=0.0, shaker=0.3, prog='a', semicorcheas=False),
    'bloque_a': dict(pad=0.95, pulso=0.5, piano=0.5, bajo=0.6, bombo=0.0, charles=0.22, caja=0.0, shaker=0.0, prog='a', semicorcheas=False,
                     patron=[0, 2, 4, 2, 1, 3, 4, 3], octava_piano=12),
    'bloque_b': dict(pad=0.9, pulso=0.42, piano=0.52, bajo=0.6, bombo=0.0, charles=0.0, caja=0.0, shaker=0.3, prog='b', semicorcheas=False,
                     patron=[0, 3, 1, 4, 2, 4, 1, 3], octava_piano=24),
    'bases': dict(pad=1.0, pulso=0.7, piano=0.65, bajo=0.85, bombo=0.35, charles=0.3, caja=0.0, shaker=0.25, prog='c', semicorcheas=False),
    'cierre': dict(pad=1.0, pulso=0.85, piano=0.8, bajo=1.0, bombo=0.8, charles=0.45, caja=0.25, shaker=0.3, prog='a', semicorcheas=True),
}


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _t(dur: float) -> np.ndarray:
    return np.arange(int(round(dur * TASA))) / TASA


def _env(n: int, ataque: float, caida: float | None = None, suelta: float = 0.0, sostener: float | None = None) -> np.ndarray:
    """Envolvente: subida en seno² de `ataque` s, caída exponencial (constante `caida` s) o meseta, y suelta final."""
    t = np.arange(n) / TASA
    e = np.ones(n)
    if ataque > 0:
        e *= np.where(t < ataque, np.sin(np.pi / 2 * np.clip(t / ataque, 0, 1)) ** 2, 1.0)
    if caida:
        e *= np.exp(-np.maximum(t - ataque, 0) / caida)
    if suelta > 0 and sostener is not None:
        e *= np.clip(1 - (t - sostener) / suelta, 0, 1) ** 2
    return e


def _paneo(x: np.ndarray, p: float) -> np.ndarray:
    """Mono a estéreo con ley de potencia constante (p de -1 a 1)."""
    a = (p + 1) * np.pi / 4
    return np.stack([x * np.cos(a), x * np.sin(a)])


# ---------------------------------------------------------------------------------------------- instrumentos
@lru_cache(maxsize=None)
def colchon(acorde: str, dur: float) -> np.ndarray:
    """Colchón cálido pero con brillo: cada nota con hasta 16 armónicos (sierra suave, los altos se abren y cierran
    despacio como un filtro que respira), dos voces desafinadas ±6 centésimas abiertas en estéreo. `dur` incluye la suelta."""
    _, notas = ACORDES[acorde]
    t = _t(dur)
    rng = np.random.default_rng(sum(ord(ch) * (k + 1) for k, ch in enumerate(acorde)))
    out = np.zeros((2, len(t)))
    barrido = 0.5 + 0.5 * np.sin(2 * np.pi * 0.07 * t - np.pi / 2)  # 0 a 1 en unos 7 s
    for k, m in enumerate(notas):
        f0 = hz(m)
        for lado, cents in ((-1, -6.0), (1, 6.0)):
            f = f0 * 2 ** (cents / 1200)
            x = np.zeros(len(t))
            for n in range(1, 17):
                if n * f > 7500:
                    break
                g = 1 / n ** 1.15
                if n > 4:
                    g *= 0.45 + 0.55 * barrido
                x += g * np.sin(2 * np.pi * n * f * t + rng.uniform(0, 2 * np.pi))
            x *= 1.0 / (1 + 0.15 * k)
            out += _paneo(x, 0.6 * lado)
    sostener = dur - 1.4
    e = _env(len(t), 0.9, None, 1.4, sostener) * (0.88 + 0.12 * np.sin(2 * np.pi * 0.11 * t))
    return out * e / 7.5


@lru_cache(maxsize=None)
def pulsado(m: int, dur: float = 0.62) -> np.ndarray:
    """Nota pulsada suave del pulso de corcheas: armónicos que se apagan antes cuanto más agudos."""
    t = _t(dur)
    f = hz(m)
    x = np.zeros(len(t))
    for n in range(1, 11):
        if n * f > 8000:
            break
        x += np.sin(2 * np.pi * n * f * t) / n ** 1.6 * np.exp(-t * (3.0 + 2.2 * n))
    return x * _env(len(t), 0.003, 0.32)


@lru_cache(maxsize=None)
def piano(m: int, dur: float = 2.6) -> np.ndarray:
    """Piano con ataque: armónicos ligeramente inarmónicos (B = 0,0004) que llegan hasta 9 kHz, los agudos se apagan
    antes y un golpe de martillo (ruido corto filtrado a 3 kHz) en el ataque."""
    t = _t(dur)
    f = hz(m)
    B = 0.0004
    x = np.zeros(len(t))
    for n in range(1, 16):
        fn = n * f * math.sqrt(1 + B * n * n)
        if fn > 9000:
            break
        x += np.sin(2 * np.pi * fn * t) / n ** 1.55 * np.exp(-t * (1.1 + 0.9 * n))
    x += 0.12 * np.sin(2 * np.pi * f * 1.002 * t) * np.exp(-t * 0.7)  # segunda cuerda
    n_m = int(0.02 * TASA)
    martillo = _paso_banda(_ruido(n_m, int(m)), 3000, 1.0) * np.exp(-np.arange(n_m) / TASA * 260)
    x[:n_m] += 0.18 * martillo / (np.max(np.abs(martillo)) + 1e-9)
    return x * _env(len(t), 0.002, None, 0.4, dur - 0.4)


@lru_cache(maxsize=None)
def bajo(m: int, dur: float) -> np.ndarray:
    t = _t(dur)
    f = hz(m)
    x = np.sin(2 * np.pi * f * t) + 0.22 * np.sin(4 * np.pi * f * t) + 0.06 * np.sin(6 * np.pi * f * t)
    return x * _env(len(t), 0.018, 1.1) * np.clip((dur - t) / 0.08, 0, 1)


@lru_cache(maxsize=None)
def bombo() -> np.ndarray:
    t = _t(0.42)
    f = 46 + 70 * np.exp(-t * 28)
    fase = 2 * np.pi * np.cumsum(f) / TASA
    return np.sin(fase) * np.exp(-t * 9.5) * _env(len(t), 0.002)


def _ruido(n: int, semilla: int) -> np.ndarray:
    return np.random.default_rng(semilla).standard_normal(n)


def _paso_alto(x: np.ndarray, fc: float) -> np.ndarray:
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / TASA)
    X *= 1 / np.sqrt(1 + (fc / np.maximum(f, 1)) ** 4)
    return np.fft.irfft(X, len(x))


def _paso_banda(x: np.ndarray, f0: float, q: float) -> np.ndarray:
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / TASA)
    X *= 1 / np.sqrt(1 + (q * (f / f0 - f0 / np.maximum(f, 1))) ** 2)
    return np.fft.irfft(X, len(x))


@lru_cache(maxsize=None)
def charles(k: int = 0) -> np.ndarray:
    n = int(0.06 * TASA)
    x = _paso_alto(_ruido(n, 11 + k), 7000)
    return x * np.exp(-np.arange(n) / TASA * 70) * 0.5


@lru_cache(maxsize=None)
def shaker(k: int = 0) -> np.ndarray:
    """Shaker suave: ruido entre 5 y 11 kHz con subida de 15 ms y caída rápida."""
    n = int(0.09 * TASA)
    t = np.arange(n) / TASA
    x = _paso_banda(_ruido(n, 41 + k), 7500, 1.4)
    return x * (np.sin(np.pi / 2 * np.clip(t / 0.015, 0, 1)) ** 2) * np.exp(-np.maximum(t - 0.015, 0) * 45) * 0.35


@lru_cache(maxsize=None)
def caja() -> np.ndarray:
    n = int(0.22 * TASA)
    t = np.arange(n) / TASA
    x = _paso_banda(_ruido(n, 23), 1800, 1.2) * np.exp(-t * 22) + 0.4 * np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30)
    return x * 0.45


# ---------------------------------------------------------------------------------------------- composición
def _poner(dest: np.ndarray, x: np.ndarray, t0: float, g: float = 1.0) -> None:
    i = int(round(t0 * TASA))
    if i >= dest.shape[-1]:
        return
    if x.ndim == 1:
        x = np.stack([x, x]) * 0.7071
    j0 = max(0, -i)
    n = min(x.shape[-1] - j0, dest.shape[-1] - max(i, 0))
    if n > 0:
        dest[:, max(i, 0):max(i, 0) + n] += g * x[:, j0:j0 + n]


MOTIVOS = [[0, None, 2, None, 4, None, 3, None], [4, None, None, 2, 3, None, 1, None], [2, None, 4, None, None, 3, 2, None]]


def seccion(tipo: str, dur: float, final: bool = False) -> np.ndarray:
    """Una sección de `dur` s que empieza en tiempo fuerte. Con `final`, los últimos compases resuelven en re."""
    E = ENERGIA[tipo]
    n = int(round(dur * TASA))
    out = np.zeros((2, n + int(3.0 * TASA)))
    prog = PROGRESIONES[E['prog']]
    ncomp = int(math.ceil(dur / COMPAS))
    rng = np.random.default_rng({'apertura': 1, 'portada': 2, 'bloque_a': 3, 'bloque_b': 4, 'bases': 5, 'cierre': 6}[tipo])
    for c in range(ncomp):
        t0 = c * COMPAS
        acorde = prog[c % len(prog)]
        if final and c >= ncomp - 2:
            acorde = 'Dfin'
        b, notas = ACORDES[acorde]
        # Colchón: un acorde nuevo solo cuando cambia (o al empezar).
        anterior = None if c == 0 else (prog[(c - 1) % len(prog)] if not (final and c - 1 >= ncomp - 2) else 'Dfin')
        if acorde != anterior:
            largo = 1
            while c + largo < ncomp and (prog[(c + largo) % len(prog)] if not (final and c + largo >= ncomp - 2) else 'Dfin') == acorde:
                largo += 1
            extra = 4.0 if (final and acorde == 'Dfin') else 1.4
            _poner(out, colchon(acorde, round(largo * COMPAS + extra, 3)), t0, E['pad'])
        # Bajo: tiempo 1 (y 3 con energía alta).
        if E['bajo']:
            golpes = (0, 2) if E['bombo'] >= 0.7 else (0,)
            for g in golpes:
                largo = 2 * TIEMPO if len(golpes) == 2 else 4 * TIEMPO
                _poner(out, bajo(b, round(largo, 3)), t0 + g * TIEMPO, 0.26 * E['bajo'])
        # Pulso: corcheas (o semicorcheas suaves) sobre las notas del acorde, una octava arriba.
        if E['pulso'] and not (final and c >= ncomp - 1):
            paso = TIEMPO / (4 if E['semicorcheas'] else 2)
            patron = E.get('patron') or [0, 2, 4, 2, 1, 3, 4, 3]
            for k in range(int(round(COMPAS / paso))):
                nota = notas[patron[k % len(patron)]] + 12
                acento = 1.0 if k % (4 if E['semicorcheas'] else 2) == 0 else 0.72
                _poner(out, _paneo(pulsado(nota), 0.35 if k % 2 else -0.35), t0 + k * paso, 0.16 * E['pulso'] * acento)
        # Piano: un motivo por compás, en el registro medio-agudo.
        if E['piano'] and c % 2 == 0 and not (final and c >= ncomp - 1):
            motivo = MOTIVOS[(c // 2) % len(MOTIVOS)]
            for k, idx in enumerate(motivo):
                if idx is None:
                    continue
                v = 0.85 + 0.15 * rng.random()
                _poner(out, _paneo(piano(notas[idx] + E.get('octava_piano', 12)), 0.15), t0 + k * TIEMPO / 2 * 2, 0.20 * E['piano'] * v)
        if final and c == ncomp - 2:
            for k, idx in enumerate((4, 3, 2)):
                _poner(out, _paneo(piano(notas[idx] + 12, 4.0), 0.1), t0 + k * TIEMPO * 0.5, 0.2 * E['piano'])
        # Percusión ligera.
        if not (final and c >= ncomp - 2):
            if E['bombo']:
                for g in (0, 2):
                    _poner(out, bombo(), t0 + g * TIEMPO, 0.55 * E['bombo'])
            if E['charles']:
                for k in range(4):
                    _poner(out, _paneo(charles(k), 0.25), t0 + (k + 0.5) * TIEMPO, 0.5 * E['charles'])
            if E.get('shaker'):
                for k in range(16):  # semicorcheas, acento en el contratiempo
                    g = 1.0 if k % 4 == 2 else (0.55 if k % 2 == 0 else 0.35)
                    _poner(out, _paneo(shaker(k % 4), -0.3), t0 + k * TIEMPO / 4, E['shaker'] * g)
            if E['caja']:
                for g in (1, 3):
                    _poner(out, caja(), t0 + g * TIEMPO, E['caja'])
    return out


def componer(secciones: list[tuple[float, float, str]], total: float, cola_final: float = 3.0) -> np.ndarray:
    """Une las secciones [(inicio, fin, tipo)]: cada una empieza en su tiempo fuerte y la anterior se apaga en
    1,2 s por debajo. La última resuelve en re y se desvanece en `cola_final` s."""
    n = int(round(total * TASA))
    out = np.zeros((2, n + int(4 * TASA)))
    for k, (t0, t1, tipo) in enumerate(secciones):
        ultima = k == len(secciones) - 1
        dur = (t1 - t0) + (0 if ultima else 1.2)
        x = seccion(tipo, dur, final=ultima)
        m = x.shape[1]
        e = np.ones(m)
        fin_i = int(round(dur * TASA))
        if not ultima:
            caida = int(1.2 * TASA)
            e[fin_i - caida:fin_i] = np.linspace(1, 0, caida) ** 2
            e[fin_i:] = 0
        else:
            caida = int(cola_final * TASA)
            e[max(0, fin_i - caida):fin_i] *= np.linspace(1, 0, min(caida, fin_i)) ** 1.5
            e[fin_i:] = 0
        sube = int(0.12 * TASA)
        if k > 0:
            e[:sube] *= np.linspace(0, 1, sube)
        _poner(out, x * e, t0)
    out = out[:, :n]
    # Paso alto a 80 Hz (nada de retumbe que enturbie la voz; los altavoces de portátil no lo dan), un poco menos de
    # medios graves (-3 dB hacia 250 Hz, donde vive el colchón) y un estante de agudos de +7 dB desde unos 2 kHz: brillo.
    for c in range(2):
        X = np.fft.rfft(out[c])
        f = np.fft.rfftfreq(n, 1 / TASA)
        X *= 1 / np.sqrt(1 + (80 / np.maximum(f, 1)) ** 4)
        X *= 1 - (1 - 10 ** (-3 / 20)) / (1 + ((f - 250) / 180) ** 2)
        X *= 1 + (10 ** (7 / 20) - 1) / (1 + (2000 / np.maximum(f, 1)) ** 2)
        out[c] = np.fft.irfft(X, n)
    return out


# ---------------------------------------------------------------------------------------------- efectos
def clic() -> np.ndarray:
    """Clic de interfaz: transitorio seco de 15 ms."""
    n = int(0.03 * TASA)
    t = np.arange(n) / TASA
    x = _paso_banda(_ruido(n, 5), 3200, 1.5) * np.exp(-t * 320) + 0.5 * np.sin(2 * np.pi * 1400 * t) * np.exp(-t * 260)
    return x / np.max(np.abs(x))


def soplo(dur: float = 0.45, sube: bool = True) -> np.ndarray:
    """Soplo de las cortinillas y los empujes: ruido filtrado que barre de grave a agudo."""
    n = int(dur * TASA)
    t = np.arange(n) / TASA
    x = _ruido(n, 9)
    trozos = np.array_split(np.arange(n), 24)
    y = np.zeros(n)
    for k, idx in enumerate(trozos):
        f0 = 300 * (12 ** (k / 23 if sube else 1 - k / 23))
        seg = _paso_banda(x, f0, 2.0)[idx]
        y[idx] = seg
    e = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.6
    y = y * e
    return y / np.max(np.abs(y))


def confirmacion() -> np.ndarray:
    """Dos notas senoidales (880 y 1320 Hz) en 220 ms: un logro real (aprobado, validado, sube de nivel)."""
    out = np.zeros(int(0.42 * TASA))
    for k, f in enumerate((880.0, 1320.0)):
        t = _t(0.3)
        x = (np.sin(2 * np.pi * f * t) + 0.18 * np.sin(4 * np.pi * f * t)) * _env(len(t), 0.004, 0.11)
        i = int(k * 0.11 * TASA)
        out[i:i + len(x)] += x
    return out / np.max(np.abs(out))


def pitido() -> np.ndarray:
    """Pitido corto de 1 kHz y 60 ms: pulsar o soltar el micrófono."""
    t = _t(0.06)
    x = np.sin(2 * np.pi * 1000 * t) * np.sin(np.pi * t / 0.06) ** 0.6
    return x / np.max(np.abs(x))


def golpe() -> np.ndarray:
    """Golpe de la portada: bombo grave con un soplo que sube antes (el soplo ocupa el primer segundo)."""
    pre = 1.0
    n = int((pre + 2.2) * TASA)
    out = np.zeros(n)
    s = soplo(pre, True) * np.linspace(0.2, 1, int(pre * TASA)) ** 2
    out[:len(s)] += 0.5 * s
    t = _t(2.2)
    f = 38 + 60 * np.exp(-t * 18)
    x = np.sin(2 * np.pi * np.cumsum(f) / TASA) * np.exp(-t * 2.6)
    x += 0.25 * _paso_banda(_ruido(len(t), 31), 900, 0.8) * np.exp(-t * 14)
    i = int(pre * TASA)
    out[i:i + len(x)] += x
    return out / np.max(np.abs(out))
