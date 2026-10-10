# Presupuesto de hardware para implantar CidIA

Precios consultados el **10 de octubre de 2026** en tiendas españolas y europeas y en páginas de fabricantes y distribuidores. Importes en euros, **con IVA (21 %)** y **sin IVA**. CidIA es software libre y no cobra por consulta, así que el único desembolso relevante es el hardware. No se incluyen la mano de obra de instalación, la formación ni el soporte.

Los tres perfiles son los de la sección «Adaptación a cada empresa» del plan y los requisitos de [`manual-servidor.md`](manual-servidor.md) §2.

**Fiabilidad de cada precio**

* **[C] Consultado**: leído hoy en la ficha o el listado de la tienda, con entrega anunciada para la semana del 13 de octubre. Precio vigente el 10/10/2026.
* **[R] Referencia**: precio de un distribuidor encontrado hoy, pero la página no fecha el precio, es de otro país o el producto puede estar agotado. Si el original no lleva IVA o lleva el de otro país, lo recalculamos con el 21 % español.
* **[E] Estimado**: no lo hemos podido confirmar; es una estimación nuestra, razonada en el texto.

> **Aviso sobre el mercado.** En octubre de 2026 las tarjetas gráficas y la memoria están muy por encima de su precio de lanzamiento. La RTX 5090 tiene un PVPR de NVIDIA de 2.369 € ([TechRadar](https://global.techradar.com/es-es/computing/gpu/nvidia-rtx-5090-comprar)) y hoy cuesta 6.999,99 € en PcComponentes. La RTX 5060 Ti de 16 GB se estimaba en 549 € antes de salir ([MuyComputer, abril de 2025](https://www.muycomputer.com/2025/04/04/precio-de-la-geforce-rtx-5060-ti-buenas-noticias/)) y hoy cuesta desde 879,99 €. Hay que repetir la consulta justo antes de comprar.

## 1. Resumen

| | Pyme pequeña | Pyme o mediana | Gran empresa |
|---|---|---|---|
| Servidor recomendado | PC de oficina sin GPU dedicada (Ryzen 7 5700G, 32 GB, 1 TB) | PC con RTX 5060 Ti de 16 GB (Ryzen 7 5800X, 32 GB, 1 TB) | Servidor torre Dell PowerEdge T560 con RTX PRO 5000 Blackwell de 48 GB |
| Servidor y SAI | 981,90 € (811,49 € sin IVA) | 1.919,90 € (1.586,69 € sin IVA) | 18.182,96 € (15.027,24 € sin IVA), con el servidor estimado |
| Modelo de IA | `ministral-3:3b` | `ministral-3:8b` con 32K | Mistral Small 3.2 24B con vLLM [E] |
| Consultas a la vez | 1 | 4 | 8 a 16 [E] |
| Puestos que atiende | 3 a 5 | 20 a 40 | 50 a 150 |
| Puesto tipo | 998,18 € (portátil profesional con funda, soporte y auriculares) | 998,18 €, o 2.568,00 € con tablet robusta | mezcla de los dos |
| **Ejemplo** | **1 servidor + 5 puestos: 6.217,78 €** (5.138,66 € sin IVA) | **1 + 5: 7.155,78 €** (5.913,87 € sin IVA)<br>**1 + 20: 22.699,47 €** (18.759,89 € sin IVA) | **1 + 50 en dos plantas** (30 normales y 20 robustos): **104.710,62 €** (86.537,70 € sin IVA) |
| Coste por puesto, con su parte de servidor, red y SAI | 1.243,56 € | 1.431,16 € (con 5) y 1.134,97 € (con 20) | 2.094,21 € |
| Electricidad al año [E] | 125 € | 201 € (con 5) y 364 € (con 20) | 962 € |

**Lo que más pesa son los puestos.** En la mediana con 20 puestos, el servidor y su SAI son el 8,5 % del total y los puestos el 87,9 %. Por eso el puesto tiene varias opciones (sección 3): un portátil profesional con funda cuesta 998 € y uno totalmente robusto, unos 4.900 €.

## 2. Modelo de IA y usuarios a la vez según la GPU

**Cómo se calcula** (informe [`04_stack_servidor_y_modelos.md`](investigacion/04_stack_servidor_y_modelos.md) §7.5, datos del MSI con 12 GB):

* Pesos de `ministral-3:8b` (Q4_K_M): 6,0 GB.
* Caché KV: 136 KiB por token en f16 y la mitad en `q8_0`. Con 32K de contexto son unos 2,2 GiB en `q8_0`, y **cada hueco de 16K para un usuario más cuesta unos 1,1 GiB**.
* Búferes y codificador de visión: 0,5 a 1 GB. Whisper `large-v3-turbo`: 1,5 a 2 GB mientras transcribe.
* Embeddings (`qwen3-embedding-cidia:0.6b`): unos 2 GB [E, a medir en el MSI]: 0,6 GB de pesos, unos 0,22 GiB de caché KV en `q8_0` con 4.096 tokens y 1,2 GiB de búferes de cálculo, que dependen del lote de 2.048 tokens y no del contexto. Es `qwen3-embedding:0.6b` con un contexto propio de 4.096 tokens ([`manual-servidor.md`](manual-servidor.md) §8.2), porque Ollama carga cada modelo con el contexto de todo el servidor y le reserva la caché KV entera. **Medido en el Oracle de pruebas** (CPU, caché KV en f16), `ollama ps` pasa de **2,9 GB** con el modelo base y contexto 8.192 (604 MiB de pesos, 896 MiB de caché KV y 1.225 MiB de búferes) a **2,4 GB** con el derivado (448 MiB de caché KV y 1.209 MiB de búferes). Con los 32K del MSI, la caché KV del modelo base ocuparía 1,75 GiB en `q8_0` y el modelo entero unos 3,6 GiB, así que el derivado ahorra allí alrededor de 1,5 GiB. Los trozos que se indexan rondan los 300 tokens, así que no se pierde nada, y los vectores son los mismos: no hay que reindexar.
* Total en el MSI: unos 11 a 11,5 GB de los 12, justo, así que caben `OLLAMA_NUM_PARALLEL=1` con 32K o `NUM_PARALLEL=2` con 16K cada uno, que ocupan lo mismo. Whisper se carga a demanda.

**De consultas a la vez a puestos atendidos [E, a medir en la fase 4 con la prueba de varios usuarios a la vez].** Una consulta con GPU ocupa su hueco unos 10 a 20 s (prompt de unos 6.000 tokens y respuesta de 500 a 40-60 tokens por segundo). Con unas 20 consultas por operario y jornada, cada puesto ocupa la GPU alrededor del 1 % de la jornada. Dejamos margen para los picos (inicio de turno, sesiones de formación) y para el procesado de capturas, que ocupa la GPU varios minutos: **un hueco por cada 5 a 10 puestos**.

| GPU (VRAM) | Ejemplo | Modelo recomendado | Reparto | Consultas a la vez | Puestos |
|---|---|---|---|---|---|
| Sin GPU, 32 GB de RAM | PC de oficina | `ministral-3:3b` (2,95 GB) y `qwen3-embedding-cidia:0.6b`; Whisper `small` int8 en CPU | `NUM_PARALLEL=1`, 16K | 1 (las demás esperan) | 3 a 5 |
| 12 GB | MSI con RTX 4080 Laptop (el MVP) | `ministral-3:8b` | 1 × 32K o 2 × 16K, Whisper a demanda | 2 | 10 a 20 |
| 16 GB | RTX 5060 Ti, RTX 5070 Ti, RTX 5080 Laptop | `ministral-3:8b` | 4 × 16K y Whisper `large-v3-turbo` siempre cargado (unos 14 GB en total) | 4 | 20 a 40 |
| 24 GB | RTX PRO 4000 Blackwell | `ministral-3:14b` [E: unos 9 GB en Q4_K_M] | 4 a 6 huecos de 16K | 4 a 6 [E] | 30 a 50 |
| 32 GB | RTX PRO 4500, Radeon AI PRO R9700 | `ministral-3:14b` con más huecos, o Mistral Small 3.2 24B [E: unos 15 GB en Q4_K_M] | 6 a 10 huecos | 6 a 10 [E] | 40 a 80 |
| 48 GB | RTX PRO 5000 Blackwell | **Mistral Small 3.2 24B** (Apache-2.0, visión y herramientas) en Q8 o FP8 [E: unos 25 GB], con vLLM | caché paginada de vLLM | 8 a 16 [E] | 50 a 150 |
| 96 GB | RTX PRO 6000 Blackwell Max-Q | Mistral Small 3.2 24B en FP8 con vLLM, o un modelo mayor | caché paginada de vLLM | 30 a 50 [E] | 150 a 400 |

Notas:

* Los tamaños de `ministral-3:14b` y de Mistral Small 3.2 no están verificados hoy: hay que leerlos en el manifiesto de `registry.ollama.ai` como en el informe 04 §7. Todos los modelos de la tabla son Apache-2.0.
* La velocidad de generación con un usuario depende sobre todo del ancho de banda de la memoria de la GPU. Según datos de fabricante (no consultados hoy), la RTX 5060 Ti (448 GB/s) está a la par que la RTX 4080 Laptop del MSI (432 GB/s), así que se esperan los mismos **40 a 60 tokens por segundo** del plan. La RTX 5070 Ti y la RTX 5080 Laptop (unos 896 GB/s) rondarían el doble [E].
* Sin GPU, la memoria del PC manda: con DDR4 de doble canal (unos 51 GB/s) `ministral-3:3b` genera como mucho unos 15 tokens por segundo, y con DDR5 (Ryzen 7 8700G, unos 90 GB/s) cerca del doble [E]. El prompt de una consulta tarda de 20 a 60 s en procesarse en 8 núcleos (en el Oracle de 4 núcleos ARM, 1-2 minutos para 8K, informe 04 §7.4) [E].
* Para la gran empresa el MVP instala Ollama; vLLM es la fase posterior prevista en el manual del servidor y es lo que permite atender muchas consultas a la vez con buena velocidad.

## 3. Componentes comunes

### 3.1 Puesto de trabajo

La app solo calcula en el servidor, así que el puesto no necesita GPU ni mucha memoria: basta un equipo Windows con Wi-Fi, micrófono y cámara.

| Opción | Modelo | Con IVA | Sin IVA | Fuente | |
|---|---|---|---|---|---|
| **A. Portátil profesional** (recomendado en zonas limpias y en la mayoría de puestos) | Lenovo ThinkPad L14 Gen 5, Ryzen 5 PRO 7535U, 16 GB, 512 GB, 14" | 739,00 € | 610,74 € | [PcComponentes](https://www.pccomponentes.com/portatiles/16-gb-ram/windows-11-pro), vendedor externo Quick Computers (confirmar que es nuevo) | [C] |
| A, más barato | HP 250R G10 15,6" (gama de consumo) | 527,98 € | 436,35 € | [PcComponentes](https://www.pccomponentes.com/portatiles/16-gb-ram/windows-11-pro) | [C] |
| **B. Tablet Windows robusta** (línea, polvo, salpicaduras) | Getac F110, 11,6", IP66, MIL-STD-810H, caídas de 1,8 m; 8 GB y 256 GB | 2.341,35 € | 1.935,00 € | [elmark-automation](https://elmark-automation.com/getac/getac-f110), «desde» | [R] |
| B, alternativa | Dell Latitude 7230 Rugged Extreme, i5-1240U, 16 GB, 256 GB | 3.055,33 € | 2.525,07 € | [Dell Irlanda](https://dell.com/en-ie/shop/dell-laptops/latitude-7230-rugged-extreme-tablet/spd/latitude-12-7230-rugged-laptop) (3.105,84 € con IVA irlandés) | [R] |
| **C. Portátil totalmente robusto** (zonas muy duras) | Getac B360, Core Ultra 5, 16 GB, 256 GB | 4.225,32 € | 3.492,00 € | [Bechtle Alemania](https://www.bechtle.com/de-en/shop/product-family/getac-b360-rugged-industrial-notebook--5581--f) | [R] |
| C, alternativa | Panasonic Toughbook 40 FZ-40BZ009B4 | 4.662,53 € | 3.853,33 € | [Lieske Elektronik](https://industry-electronics.com/panasonic/fz-40bz009b4-toughbook-40-printview-282784.htm) | [R] |

Accesorios del puesto:

| Accesorio | Modelo | Con IVA | Sin IVA | Fuente | |
|---|---|---|---|---|---|
| Funda o carcasa para la opción A | Funda acolchada resistente o carcasa rígida de 14" | 60,00 € | 49,59 € | sin consultar | [E] |
| Soporte en el puesto | Soporte de sobremesa con brazo y bandeja para portátil (VESA 75 y 100, portátil de hasta 17") | 32,53 € | 26,88 € | [PcComponentes MP01](https://www.pccomponentes.com/soporte-de-escritorio-con-brazos-para-portatil-y-para-monitor-mp01) | [R] |
| Soporte, solo bandeja | Bandeja VESA para un brazo o poste ya existente | 6,99 € | 5,78 € | [PcCom Essential](https://www.pccomponentes.com/pccom-essential-soporte-bandeja-de-portatil-compatible-vesa-75x75-100x100-negro) | [R] |
| Soporte para tablet | Adaptador VESA para tablet o base del fabricante | 60,00 € | 49,59 € | sin consultar | [E] |

### 3.2 Auriculares con micrófono para ruido

| Opción | Modelo | Con IVA | Sin IVA | Fuente | |
|---|---|---|---|---|---|
| **Ruido moderado** (recomendado) | Jabra Evolve2 65 Flex Duo, Bluetooth, cancelación activa de ruido y micrófono con supresión de ruido | 166,65 € | 137,73 € | [alternate.de](https://www.alternate.de/Jabra/Evolve2-65-Flex-Duo-Headset/html/product/1906937) (163,90 € con IVA alemán; la variante con base de carga está a 238,90 € y agotada) | [R] |
| **Ruido alto** (donde el protector auditivo es obligatorio, a partir de 85 dB(A) según el RD 286/2006) | 3M Peltor WS Alert XPI MRX21A3WS6, protector SNR 30 dB con Bluetooth y micrófono | 652,46 € | 539,22 € | [M&W, Dinamarca](https://ehandel.mw.dk/en/hearing-protection-and-earplugs/3m-peltor-ws-alert-xpi-bt-hoerevaern-mapp-boejle) | [R] |

El Peltor es a la vez EPI y auricular, así que en zonas ruidosas sustituye al protector que ya lleva el operario.

### 3.3 Red

| Opción | Modelo | Con IVA | Sin IVA | Fuente | |
|---|---|---|---|---|---|
| **Punto de acceso de interior** (recomendado) | Ubiquiti U7 Pro, Wi-Fi 7 tribanda, PoE+ | 221,99 € | 183,46 € | [PcComponentes](https://www.pccomponentes.com/marcas/ubiquiti/puntos-acceso-wifi) | [C] |
| Más barato | Ubiquiti U7 Lite, Wi-Fi 7 | 119,99 € | 99,17 € | ídem | [C] |
| Exterior o nave abierta | Ubiquiti U7 Outdoor, Wi-Fi 7 | 229,99 € | 190,07 € | ídem | [C] |
| **Punto de acceso industrial** (carril DIN, para gran empresa) | Moxa AWK-1137C | 703,71 € | 581,58 € | [RS Bélgica](https://befr.rs-online.com/web/p/wireless-access-points/0634950) | [R] |
| Alimentación de un solo punto de acceso | Inyector PoE+ Ubiquiti U-POE-AT, 30 W | 22,99 € | 19,00 € | [PcComponentes](https://www.pccomponentes.com/marcas/ubiquiti/puntos-acceso-wifi) | [C] |
| Switch | Switch PoE+ gestionable de 8 puertos | 150,00 € | 123,97 € | sin consultar | [E] |
| Switch industrial | Switch gestionable de 8 puertos para carril DIN | 500,00 € | 413,22 € | sin consultar | [E] |

El servidor va por cable a la red de la empresa (manual del servidor §2). En la pyme pequeña se aprovecha el router existente.

### 3.4 SAI

| Opción | Modelo | Con IVA | Sin IVA | Fuente | |
|---|---|---|---|---|---|
| Mini PC con alimentador externo | Salicru SPS One 1100 VA V2 (la ficha del SPS One de 1500 VA lo da como **no compatible con fuentes APFC**, así que la familia no sirve para un PC de sobremesa) | 119,14 € | 98,46 € | [PcComponentes](https://www.pccomponentes.com/marcas/salicru/sais) | [C] |
| **PC de oficina** (perfil 1) | Salicru SPS Advance T 1000 VA, de la misma familia que el de 1500 VA | 262,90 € | 217,27 € | ídem | [C] |
| **PC con GPU** (perfil 2) | Salicru SPS Advance T 1500 VA, senoidal pura, compatible con fuentes APFC | 290,90 € | 240,41 € | ídem, vendedor externo Quierotek | [C] |
| **Servidor** (perfil 3) | Salicru SLC-2000-TWIN RT3, on-line de doble conversión | 975,90 € | 806,53 € | ídem | [C] |
| Servidor con dos GPU | Salicru SLC 3000 Twin RT3, 3000 VA y 3000 W, doble conversión | 1.172,90 € | 969,34 € | ídem | [C] |
| Alternativa de otra marca | APC Smart-UPS SMT1500IC, 1500 VA y 1000 W (justo para un servidor con GPU) | 843,52 € | 697,12 € | [Unieuro](https://www.unieuro.it/online/UPS/SMT1500IC-pidAPCSMT1500IC) (850,49 € con IVA italiano) | [R] |

### 3.5 Opcional: captura de vídeo

| Opción | Modelo | Con IVA | Sin IVA | Fuente | |
|---|---|---|---|---|---|
| Sin coste | La cámara del portátil o el móvil de empresa que ya exista | 0,00 € | 0,00 € | | |
| **Móvil robusto para grabar en planta** | Samsung Galaxy XCover7 Pro, 6 GB y 128 GB | 394,00 € | 325,62 € | [Kimovil](https://www.kimovil.com/es/donde-comprar-samsung-galaxy-xcover-7-pro) (desde 359 € según el día) | [R] |
| Trípode o pinza para el móvil | | 25,00 € | 20,66 € | sin consultar | [E] |

Un kit de captura (móvil y trípode) cuesta 419,00 € (346,28 € sin IVA). Basta uno por cada técnico que documenta, no uno por puesto.

## 4. Perfil 1: pyme pequeña (sin GPU dedicada)

Para captura, consulta e instrucciones de los puestos críticos, con respuestas lentas (sección 2).

| Componente | Elección | Con IVA | Sin IVA | Fuente | |
|---|---|---|---|---|---|
| **Servidor** | PcCom Work AMD Ryzen 7 5700G (8 núcleos), 32 GB, SSD de 1 TB | 719,00 € | 594,21 € | [PcComponentes](https://www.pccomponentes.com/sobremesa/32-gb-ram/stock) | [C] |
| Servidor, más rápido | PcCom Work AMD Ryzen 7 8700G, 32 GB DDR5, SSD de 1 TB, Windows 11 Home | 1.049,00 € | 866,94 € | ídem | [C] |
| Servidor, compacto | Mini PC GMKtec NucBox K8 Plus, Ryzen 7 8845HS, 32 GB, 1 TB | 806,57 € | 666,58 € | [PcComponentes Francia](https://www.pccomponentes.fr/mini-pc/32-gb-ram/amd-ryzen-7) (799,90 € con IVA francés) | [R] |
| Puesto (× 5) | Opción A: ThinkPad L14 Gen 5, funda, soporte MP01 y Jabra Evolve2 65 Flex | 998,18 € cada uno | 824,94 € | sección 3 | [C], [R] y [E] |
| Red | Ubiquiti U7 Pro e inyector PoE+ | 244,98 € | 202,46 € | sección 3.3 | [C] |
| SAI | Salicru SPS Advance T 1000 VA | 262,90 € | 217,27 € | sección 3.4 | [C] |
| Opcional | Kit de captura | 419,00 € | 346,28 € | sección 3.5 | [R] y [E] |

**Ejemplo, 1 servidor + 5 puestos: 6.217,78 € con IVA (5.138,66 € sin IVA)**, es decir, **1.243,56 € por puesto** (1.027,73 € sin IVA). Con el kit de captura, 6.636,78 €. Con el Ryzen 7 8700G en lugar del 5700G, 330 € más.

El PC de 719 € trae solo DDR4: si la empresa quiere respuestas más ágiles sin pagar una GPU, el 8700G con DDR5 es la mejor mejora por euro [E]. Los tres equipos sirven también para empezar y pasar después a un servidor con GPU sin reprocesar los documentos, porque todos los perfiles usan el mismo modelo de embeddings.

## 5. Perfil 2: pyme o mediana (GPU de 12 a 16 GB)

Todo CidIA para un centro y varios puestos. Es la configuración del MVP, con una GPU de 16 GB en lugar de los 12 del MSI.

| Componente | Elección | Con IVA | Sin IVA | Fuente | |
|---|---|---|---|---|---|
| **Servidor** | PcCom Ready AMD Ryzen 7 5800X, 32 GB, SSD de 1 TB, **RTX 5060 Ti de 16 GB**, Windows 11 Home | 1.629,00 € | 1.346,28 € | [PcComponentes](https://www.pccomponentes.com/categorias/sobremesa/geforce-rtx-5060-ti) | [C] |
| Servidor, el doble de rápido | El mismo PC con RTX 5070 Ti de 16 GB (la tarjeta sola, desde 1.379,00 € [C] en [PcComponentes](https://www.pccomponentes.com/tarjetas-graficas/geforce-rtx-5060/geforce-rtx-5070-ti/nuevo/stock), frente a 879,99 € de la 5060 Ti [C] en [PcComponentes](https://www.pccomponentes.com/tarjetas-graficas/geforce-rtx-5060-ti)) | 2.130,00 € | 1.760,33 € | cálculo con las dos tarjetas | [E] |
| Servidor portátil, como el MSI | PcCom Legend 5080 16", Core Ultra 9 275HX, 32 GB, 1 TB, RTX 5080 de 16 GB | 2.849,99 € | 2.355,36 € | [PcComponentes](https://pccomponentes.com/portatiles/geforce-rtx-5080-series) | [C] |
| Servidor portátil MSI | MSI Vector 18 HX AI A2XWIG-648ES, Core Ultra 9 275HX, 32 GB, 1 TB, RTX 5080 | 3.274,60 € | 2.706,28 € | ídem | [C] |
| Puesto | Opción A (998,18 €) o, en la línea, opción B con tablet Getac F110, soporte y Jabra (2.568,00 €) | | | sección 3 | |
| Red con 5 puestos | Ubiquiti U7 Pro e inyector PoE+ | 244,98 € | 202,46 € | sección 3.3 | [C] |
| Red con 20 puestos | 3 Ubiquiti U7 Pro y switch PoE+ de 8 puertos | 815,97 € | 674,36 € | sección 3.3 | [C] y [E] |
| SAI | Salicru SPS Advance T 1500 VA | 290,90 € | 240,41 € | sección 3.4 | [C] |
| Opcional | 1 o 2 kits de captura | 419,00 € cada uno | 346,28 € | sección 3.5 | [R] y [E] |

**Ejemplos:**

* **1 servidor + 5 puestos: 7.155,78 € con IVA (5.913,87 € sin IVA)**, 1.431,16 € por puesto.
* **1 servidor + 20 puestos: 22.699,47 € con IVA (18.759,89 € sin IVA)**, **1.134,97 € por puesto** (937,99 € sin IVA). El servidor y el SAI son el 8,5 % del total.
* 20 puestos con 5 tablets robustas en la línea y 15 portátiles: 30.548,57 € (25.246,75 € sin IVA), 1.527,43 € por puesto.

**Por qué un sobremesa y no un portátil como el MSI.** Da los mismos 16 GB de VRAM por 1.221 € menos que el portátil con RTX 5080 más barato, se refrigera mejor funcionando día y noche y la batería no se degrada. El portátil solo compensa si el servidor se tiene que mover (demos, varios centros). El PC trae Windows 11 Home, que no se usa porque el servidor va con Ubuntu: en julio había una versión sin Windows a 1.529 € ([R], misma página), así que conviene buscarla. Los 32 GB de RAM y 1 TB de disco cumplen los requisitos del manual (32 GB y 150 GB libres).

## 6. Perfil 3: gran empresa (servidor Linux con GPU, varios usuarios y plantas)

| Componente | Elección | Con IVA | Sin IVA | Fuente | |
|---|---|---|---|---|---|
| **Servidor** | Dell PowerEdge T560 (torre de 4,5U, seis ranuras PCIe, admite dos GPU de doble ancho y 300 W) con un Xeon de 16 núcleos, 128 GB DDR5 RDIMM, dos NVMe de 1,92 TB en RAID 1 y doble fuente. La base cuesta de 2.405 a 2.905 € sin IVA en [Servermall](https://servermall.com/es/config/dell-t560-8lff-new/) [R]; la configuración completa es nuestra estimación | 7.260,00 € | 6.000,00 € | Servermall y [StorageReview](https://www.storagereview.com/es/review/dell-poweredge-t560-tower-server-review) | [E] |
| **GPU recomendada, 48 GB** | NVIDIA RTX PRO 5000 Blackwell 48 GB (PNY) | 9.947,06 € | 8.220,71 € | [PcComponentes](https://www.pccomponentes.com/categorias/tarjetas-graficas/para-ia-machine-learning?page=2), vendedor externo NOWBUY | [C] |
| GPU, 24 GB | PNY RTX PRO 4000 Blackwell 24 GB | 2.970,00 € | 2.454,55 € | ídem, vendedor INSTYLEANDJOY | [C] |
| GPU, 32 GB | NVIDIA RTX PRO 4500 Blackwell 32 GB Server Edition | 5.347,00 € | 4.419,01 € | ídem, vendedor Leasi-es | [C] |
| GPU, 96 GB | PNY RTX PRO 6000 Blackwell Max-Q 96 GB (300 W; la versión Workstation de 600 W supera lo que admite el T560) | 20.255,99 € | 16.740,49 € | [PcComponentes](https://www.pccomponentes.com/categorias/tarjetas-graficas/para-ia-machine-learning), vendedor NOWBUY | [C] |
| GPU, 96 GB, más barata | La misma, en Amazon.de (mediana de tres meses: 14.600 €) | 16.719,00 € | 13.817,36 € | [gpuprix](https://gpuprix.com/eu/gpus/rtx-pro-6000-blackwell), actualizado el 7/10/2026 | [R] |
| GPU alternativa AMD, 64 GB | 2 × XFX Radeon AI PRO R9700 de 32 GB | 4.599,98 € | 3.801,64 € | [PcComponentes](https://www.pccomponentes.com/categorias/tarjetas-graficas/para-ia-machine-learning) | [C] |
| Descartada | RTX 5090 de 32 GB: 6.999,99 € [C], más cara que la RTX PRO 4500 de 32 GB y diseñada para sobremesa | | | ídem | |
| Puestos | Opción A en zonas limpias y opción B o C en la línea | | | sección 3 | |
| Red (dos plantas) | 6 Moxa AWK-1137C y 2 switches industriales de 8 puertos | 5.222,26 € | 4.315,92 € | sección 3.3 | [R] y [E] |
| Red, alternativa | 6 Ubiquiti U7 Outdoor y 2 switches PoE+ | 1.679,94 € | 1.388,38 € | sección 3.3 | [C] y [E] |
| SAI | Salicru SLC-2000-TWIN RT3, on-line | 975,90 € | 806,53 € | sección 3.4 | [C] |

**Ejemplo adicional, 1 servidor + 50 puestos en dos plantas** (30 de la opción A y 20 tablets de la opción B): **104.710,62 € con IVA (86.537,70 € sin IVA)**, **2.094,21 € por puesto**. El servidor con su SAI son el 17,4 %.

Notas:

* **Por qué 48 GB.** Es el salto de calidad que pide el plan («uno mayor con 24-48 GB»): Mistral Small 3.2 24B con buena cuantización y vLLM para 8 a 16 consultas a la vez [E]. La de 96 GB cuesta el doble y solo compensa con cientos de puestos o con un modelo mucho mayor.
* **La alternativa AMD** es la más barata por GB, pero exige ROCm. Ollama y vLLM lo admiten, mientras que el servicio `asr` (faster-whisper sobre CTranslate2) necesita CUDA, así que Whisper iría a la CPU del servidor [E, sin probar].
* **El servidor está estimado.** Con la memoria tan cara en 2026, hay que pedir presupuesto cerrado a Dell o a un distribuidor (y, para comparar, a Lenovo con un ThinkSystem de torre) con la configuración exacta, y comprobar que la GPU elegida está certificada para ese chasis (flujo de aire y cables de alimentación).
* La integración con el directorio de la empresa, el MES, la GMAO y el LMS es software y no cambia el hardware.

## 7. Coste recurrente

No hay licencias por consulta ni por usuario: Ubuntu, Docker, Ollama, los modelos y CidIA son libres. El Windows de los puestos viene incluido en su precio. El único gasto recurrente relevante es la electricidad.

**Precio de la electricidad [E]: 0,18 €/kWh sin IVA**, sin contar el impuesto eléctrico. Es un valor intermedio entre los periodos de una tarifa 3.0TD de pyme (0,2072 €/kWh en P1 y 0,1324 €/kWh en P6, Naturgy) y la oferta de Endesa para más de 15 kW (0,1675 €/kWh), recogidas por [Selectra](https://selectra.es/empresas/tarifas-luz). Como referencia, el mercado mayorista se prevé en unos 0,055 €/kWh de media en 2026 ([ASE, en Energías Renovables](https://www.energias-renovables.com/panorama/el-precio-de-la-electricidad-en-espa-20260107)). El servidor no obliga a subir la potencia contratada.

| Equipo | Potencia media [E] | Horas al año | kWh al año | Sin IVA | Con IVA |
|---|---|---|---|---|---|
| PC sin GPU, encendido siempre | 30 W | 8.760 | 263 | 47,30 € | 57,24 € |
| PC con RTX 5060 Ti, encendido siempre y casi siempre en reposo | 70 W | 8.760 | 613 | 110,38 € | 133,55 € |
| Portátil tipo MSI como servidor | 45 W | 8.760 | 394 | 70,96 € | 85,86 € |
| Servidor T560 con RTX PRO 5000 | 230 W | 8.760 | 2.015 | 362,66 € | 438,82 € |
| Puesto (8 h y 225 días) | 15 W | 1.800 | 27 | 4,86 € | 5,88 € |
| Punto de acceso | 12 W | 8.760 | 105 | 18,92 € | 22,90 € |
| Switch PoE+ (sin contar lo que entrega por PoE) | 15 W | 8.760 | 131 | 23,65 € | 28,62 € |
| Pérdidas del SAI de línea interactiva | 8 W | 8.760 | 70 | 12,61 € | 15,26 € |

| Ejemplo | Electricidad al año, sin IVA | Con IVA |
|---|---|---|
| Pyme pequeña, 1 + 5 | 103,14 € | 124,80 € |
| Pyme o mediana, 1 + 5 | 166,21 € | 201,12 € |
| Pyme o mediana, 1 + 20 | 300,61 € | 363,73 € |
| Gran empresa, 1 + 50 (6 puntos de acceso industriales de 10 W y SAI on-line con 30 W de pérdidas) | 794,88 € | 961,80 € |

Otros gastos previsibles [E]: baterías del SAI cada 3 a 5 años (40 a 80 € en los de línea interactiva y 150 a 300 € en los on-line) y, si se quiere, la ampliación de garantía del servidor.

## 8. Comparación con la nube de pago por uso

**Supuestos de uso [E]:** 20 consultas por puesto y día laborable, 225 días al año, 6.000 tokens de entrada por consulta (prompt de sistema con herramientas, fragmentos recuperados y contexto del paso) y 500 de salida. Con 20 puestos son 90.000 consultas, 540 millones de tokens de entrada y 45 de salida al año. No contamos imágenes, transcripción (en la nube ronda 0,003 a 0,006 $ por minuto [E]) ni la generación de instrucciones desde vídeo. Cambio: 1 $ ≈ 0,86 € [E].

Precios de la API de Mistral (la familia de nuestro modelo), según rastreadores que citan la tarifa oficial: Ministral 3 8B a 0,15 $ por millón de tokens de entrada y de salida ([pricepertoken, agosto de 2026](https://pricepertoken.com/pricing-page/model/mistral-ai-ministral-8b)); Mistral Medium 3.5 a 1,50 $ de entrada y 7,50 $ de salida ([BenchLM, julio de 2026](https://benchlm.ai/mistral/api-pricing)) [R]. Servidores GPU dedicados de Hetzner, en Alemania: GEX45 con RTX PRO 4000 de 24 GB a 214 €/mes y 209 € de alta ([nota de prensa de Hetzner, 1/9/2026](https://www.hetzner.com/pressroom/hetzner-expands-its-gpu-portfolio-with-the-gex45/)); GEX63 con RTX PRO 6000 Max-Q de 96 GB a 999 €/mes y 999 € de alta ([nota de prensa de Hetzner, 6/10/2026](https://www.hetzner.com/pressroom/hetzner-expands-gpu-portfolio-with-new-gex63-featuring-nvidia-rtx-pro-6000-blackwell-max-q/)), todo sin IVA [R].

| Coste anual sin IVA | 5 puestos | 20 puestos | 50 puestos | 200 puestos |
|---|---|---|---|---|
| API con Ministral 3 8B (el modelo del MVP) | unos 19 € | unos 75 € | unos 189 € | unos 755 € |
| API con Mistral Medium 3.5 (modelo grande) | unos 247 € | unos 987 € | unos 2.467 € | unos 9.868 € |
| Servidor GPU dedicado GEX45, 24 GB (primer año) | 2.777 € | 2.777 € | 2.777 € | no alcanza |
| Servidor GPU dedicado GEX63, 96 GB (primer año) | | | 12.987 € | 12.987 € |
| **CidIA en local**, mediana: PC con RTX 5060 Ti y SAI amortizados en 4 años y su electricidad | 507 € | 507 € | | |
| **CidIA en local**, gran empresa: T560 con RTX PRO 5000 y SAI amortizados en 4 años y su electricidad | | | 4.119 € | 4.119 € |

**Lectura honesta:**

* **En tokens, la API de un modelo pequeño es barata**: con 20 puestos, Ministral 3 8B en la nube costaría unos 75 € al año, menos que amortizar el PC. La ventaja de CidIA no es el precio por token, sino que **los documentos, vídeos y preguntas de la empresa no salen de su red** (las bases los consideran suyos y confidenciales), que funciona aunque falle Internet en la planta y que el coste no crece con el uso, así que se puede animar a todo el mundo a preguntar.
* **Con un modelo grande la API ya pesa**: unos 2.500 € al año con 50 puestos y casi 10.000 € con 200, y sube cada vez que se añaden puestos, imágenes o vídeo.
* **Lo comparable con CidIA es un servidor GPU dedicado**, en el que los datos también quedan aislados. Con IVA, el PC de la mediana (1.919,90 €) se paga en **unos 8 meses** de GEX45, y el servidor de la gran empresa (18.182,96 €) en **unos 15 meses** de GEX63. A partir de ahí, en local solo se paga la luz.
* En cualquier caso, **los puestos y la red hacen falta igual** con la nube, y son entre el 73 y el 92 % del presupuesto según el ejemplo.

## 9. Fuentes

Todas consultadas el 10/10/2026.

**Consultadas en la página de la tienda [C]**

* PcComponentes, tarjetas para IA, páginas [1](https://www.pccomponentes.com/categorias/tarjetas-graficas/para-ia-machine-learning) y [2](https://www.pccomponentes.com/categorias/tarjetas-graficas/para-ia-machine-learning?page=2): RTX 5090, Radeon AI PRO R9700, RTX PRO 4000, 4500, 5000 y 6000.
* PcComponentes, [RTX 5060 Ti](https://www.pccomponentes.com/tarjetas-graficas/geforce-rtx-5060-ti) y [RTX 5070 Ti](https://www.pccomponentes.com/tarjetas-graficas/geforce-rtx-5060/geforce-rtx-5070-ti/nuevo/stock).
* PcComponentes, [sobremesa con RTX 5060 Ti](https://www.pccomponentes.com/categorias/sobremesa/geforce-rtx-5060-ti), [sobremesa con 32 GB](https://www.pccomponentes.com/sobremesa/32-gb-ram/stock), [portátiles con RTX 5080](https://pccomponentes.com/portatiles/geforce-rtx-5080-series) y [portátiles con 16 GB y Windows 11 Pro](https://www.pccomponentes.com/portatiles/16-gb-ram/windows-11-pro).
* PcComponentes, [puntos de acceso Ubiquiti](https://www.pccomponentes.com/marcas/ubiquiti/puntos-acceso-wifi) y [SAI Salicru](https://www.pccomponentes.com/marcas/salicru/sais).
* Hetzner, [nota de prensa del GEX45](https://www.hetzner.com/pressroom/hetzner-expands-its-gpu-portfolio-with-the-gex45/) (1/9/2026).
* alternate.de, [Jabra Evolve2 65 Flex Duo WLC](https://www.alternate.de/Jabra/Evolve2-65-Flex-Duo-WLC-mit-Ladepad-Headset/html/product/1906940): 238,90 €, agotado.

**Referencias de distribuidor encontradas en buscador [R]**

* [gpuprix, RTX PRO 6000 Blackwell en Europa](https://gpuprix.com/eu/gpus/rtx-pro-6000-blackwell) (actualizado el 7/10/2026).
* [Servermall, Dell PowerEdge T560](https://servermall.com/es/config/dell-t560-8lff-new/) y [StorageReview, análisis del T560](https://www.storagereview.com/es/review/dell-poweredge-t560-tower-server-review).
* [PcComponentes Francia, mini PC con Ryzen 7 y 32 GB](https://www.pccomponentes.fr/mini-pc/32-gb-ram/amd-ryzen-7).
* [Bechtle, Getac B360](https://www.bechtle.com/de-en/shop/product-family/getac-b360-rugged-industrial-notebook--5581--f); [Lieske, Toughbook 40](https://industry-electronics.com/panasonic/fz-40bz009b4-toughbook-40-printview-282784.htm); [Dell Irlanda, Latitude 7230 Rugged Extreme](https://dell.com/en-ie/shop/dell-laptops/latitude-7230-rugged-extreme-tablet/spd/latitude-12-7230-rugged-laptop); [elmark-automation, Getac F110](https://elmark-automation.com/getac/getac-f110).
* [alternate.de, Jabra Evolve2 65 Flex Duo](https://www.alternate.de/Jabra/Evolve2-65-Flex-Duo-Headset/html/product/1906937); [M&W, 3M Peltor WS Alert XPI](https://ehandel.mw.dk/en/hearing-protection-and-earplugs/3m-peltor-ws-alert-xpi-bt-hoerevaern-mapp-boejle).
* [RS Bélgica, Moxa AWK-1137C](https://befr.rs-online.com/web/p/wireless-access-points/0634950); [Unieuro, APC SMT1500IC](https://www.unieuro.it/online/UPS/SMT1500IC-pidAPCSMT1500IC).
* [Kimovil, Samsung Galaxy XCover7 Pro](https://www.kimovil.com/es/donde-comprar-samsung-galaxy-xcover-7-pro).
* PcComponentes, [soporte MP01](https://www.pccomponentes.com/soporte-de-escritorio-con-brazos-para-portatil-y-para-monitor-mp01) y [bandeja PcCom Essential](https://www.pccomponentes.com/pccom-essential-soporte-bandeja-de-portatil-compatible-vesa-75x75-100x100-negro) (capturas con entrega en agosto).
* [Selectra, tarifas de luz para empresas](https://selectra.es/empresas/tarifas-luz); [Energías Renovables, previsión de ASE para 2026](https://www.energias-renovables.com/panorama/el-precio-de-la-electricidad-en-espa-20260107).
* [pricepertoken, Ministral 8B](https://pricepertoken.com/pricing-page/model/mistral-ai-ministral-8b); [BenchLM, precios de la API de Mistral](https://benchlm.ai/mistral/api-pricing). Conviene contrastarlos con la [tarifa oficial de Mistral](https://docs.mistral.ai/platform/pricing), que no hemos consultado.
* [Hetzner, nota de prensa del GEX63](https://www.hetzner.com/pressroom/hetzner-expands-gpu-portfolio-with-new-gex63-featuring-nvidia-rtx-pro-6000-blackwell-max-q/) (6/10/2026; precio leído en el resumen del buscador).
* [TechRadar, PVPR de la RTX 5090](https://global.techradar.com/es-es/computing/gpu/nvidia-rtx-5090-comprar); [MuyComputer, precio previsto de la RTX 5060 Ti](https://www.muycomputer.com/2025/04/04/precio-de-la-geforce-rtx-5060-ti-buenas-noticias/).

**Del proyecto**

* [`investigacion/04_stack_servidor_y_modelos.md`](investigacion/04_stack_servidor_y_modelos.md) §7.4 y §7.5: tamaños de los modelos, caché KV y reparto de la VRAM.
* [`manual-servidor.md`](manual-servidor.md) §2: requisitos por tipo de empresa.
