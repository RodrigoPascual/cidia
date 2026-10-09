"""Documentos de conocimiento sintéticos (Markdown sencillo; los de formato «pdf» se convierten).

Contenido inventado para Metalúrgica Arlanza, S. L. (ficticia). A propósito, ningún documento
explica la presión del cilindro de la prensa 2 ni cómo se purga el circuito de refrigeración:
son las lagunas de la demostración.

Campos: clave, titulo, fichero, formato (md | pdf), departamento (clave o None), nivel,
formacion, publico, autor, subido_por, dias (antigüedad), descripcion, cabecera (pdf) y texto.
"""

from __future__ import annotations

AVISO = ("> Documento sintético de demostración. Metalúrgica Arlanza, S. L. es una empresa ficticia; "
         "personas, proveedores, precios y referencias son inventados.")

BIENVENIDA = f"""# Bienvenida y prevención de riesgos laborales

{AVISO}

## Quiénes somos

Metalúrgica Arlanza fabrica conjuntos metálicos estampados, soldados y montados para fabricantes de maquinaria agrícola y de equipos de climatización. Trabajamos en una única planta en un polígono industrial de Burgos, con unas 60 personas en tres turnos.

La planta se organiza en cuatro departamentos: **Producción** (prensas, línea 2 de montaje y soldadura), **Oficina técnica** (utillajes, planos y procesos), **Calidad** (laboratorio e inspección en línea) y **Mantenimiento** (mecánico y eléctrico).

## Distribución de la planta

| Zona | Qué hay | EPIs obligatorios |
|---|---|---|
| Nave 1 · Prensas | Prensas P1 (250 t), P2 (400 t), P3 (630 t) y P4 (160 t), almacén de moldes | Calzado S3, protección auditiva, guantes anticorte, gafas |
| Nave 2 · Línea 2 | Montaje de colectores CL-200: estaciones E1 a E6 | Calzado S3, guantes de protección mecánica, gafas |
| Nave 2 · Soldadura | Puestos MAG manuales y célula robotizada R2 | Pantalla de soldar, guantes de soldador, mandil, calzado S3 |
| Laboratorio | Mesa de medición, banco de par, armario de calibres | Calzado de seguridad en tránsito por planta |
| Oficina técnica | Planta alta, puestos de CAD | Ninguno en oficina; los de la zona al bajar a planta |

## Horarios y turnos

- Turno de mañana: de 6:00 a 14:00. Turno de tarde: de 14:00 a 22:00.
- Turno de noche (solo prensas, de lunes a jueves): de 22:00 a 6:00.
- El relevo se hace **en el puesto**: quien entra recibe de quien sale el estado de la máquina, las incidencias y las piezas pendientes de control.

## Normas básicas de seguridad

1. Usa siempre los EPIs de la zona, también si solo vas de paso.
2. Camina por los pasillos peatonales marcados en verde. Los pasillos amarillos son de carretillas: cruza solo por los pasos señalizados y establece contacto visual con el conductor.
3. Nunca metas las manos en una máquina en marcha ni anules un resguardo o una barrera fotoeléctrica.
4. Antes de cualquier intervención dentro de una máquina, **consigna** sus energías con tu candado personal (procedimiento de consignación de Mantenimiento). Un candado, una persona, una llave.
5. Mantén el puesto en orden: lo que no se usa, fuera; cada herramienta en su sombra del panel; derrames limpios al momento.
6. Comunica cualquier incidente o casi accidente a tu responsable en el mismo turno. También puedes dejarlo como aportación en CidIA.

## Emergencias

- Teléfono interno de emergencias: extensión **200** (portería, atendida las 24 horas). Desde un móvil, 112.
- Punto de reunión: **aparcamiento norte (P-1)**, junto a la portería.
- Extintores y bocas de incendio señalizados en cada columna par de las naves. Lavaojos en prensas, soldadura y laboratorio.
- Botiquines en portería, nave 1 (columna 8) y nave 2 (columna 14). Primeros auxilios: personas formadas en cada turno, con brazalete verde.

## Cómo usar CidIA

CidIA es el copiloto de conocimiento de la planta. Puedes preguntarle por voz o por escrito en tu puesto. Sus respuestas citan la fuente (instrucción, paso, documento o aportación validada) para que puedas comprobarla. Si no encuentra respaldo en la documentación, te lo dice con claridad y registra la pregunta para que el responsable la resuelva. Lo que aprendes con el uso queda en tu progreso; nadie te va a juzgar por preguntar.

## Tus primeros días

| Día | Qué harás | Con quién |
|---|---|---|
| 1 | Acogida, entrega de EPIs, recorrido por la planta y esta guía | Responsable de tu departamento |
| 2 | Formación de seguridad de tu puesto y consignación | Mantenimiento |
| 3 a 5 | Itinerario de formación en CidIA y prácticas acompañadas | Persona experta del puesto |
| 10 | Primera observación en el puesto y revisión de dudas | Responsable de tu departamento |
"""

MANUAL_OT = f"""# Manual de iniciación a Oficina técnica

{AVISO}

## Para qué sirve la Oficina técnica

La Oficina técnica (OT) convierte lo que pide el cliente en algo que la planta puede fabricar: revisa los planos de cliente, diseña los utillajes de soldadura y control, define las hojas de proceso y da de alta las referencias en el ERP. También responde a las dudas técnicas de Producción y Calidad.

Responsable del departamento: **Ana López**. Puestos: Diseño de utillajes e Ingeniería de procesos.

## Herramientas de trabajo

- **CAD 3D corporativo** con la biblioteca de componentes normalizados (amarres, apoyos, casquillos, tornillería).
- **Gestor documental de planos (PDM)**: ningún plano sale de la OT sin estar liberado en el PDM.
- **ERP**: artículos, listas de materiales y rutas.
- **CidIA**: consulta de procedimientos, instrucciones de trabajo y lecciones aprendidas.

## Codificación

| Elemento | Formato | Ejemplo |
|---|---|---|
| Utillaje | UT-AAAA-NNN | UT-2025-014 (utillaje de soldadura de soportes SL-12) |
| Plano de pieza propia | PL-NNNNN | PL-20311 (brida B) |
| Plantilla de CAD de utillajes | UT-PLANTILLA-03 | Plantilla con cajetín, capas y lista de materiales |
| Hoja de proceso | HP-referencia | HP-CL-200 |
| Revisión de plano | Letra A, B, C... | La revisión A es la primera liberada |

## Tolerancias y acabados por defecto

Salvo que el plano indique otra cosa, se aplican las **tolerancias generales ISO 2768-mK**. Las superficies de apoyo de los utillajes llevan rugosidad Ra 1,6 y las de contacto con la pieza se rectifican. Los apoyos que sufren desgaste se fabrican en acero templado.

## El sistema de referencias 3-2-1

Para que una pieza quede siempre en la misma posición en un utillaje, se eliminan sus seis grados de libertad con seis puntos de apoyo:

1. **Tres puntos** en el plano principal (el más grande y estable) fijan la altura y dos giros.
2. **Dos puntos** en un plano lateral fijan un desplazamiento y el giro restante.
3. **Un punto** en el tercer plano fija el último desplazamiento.

Los amarres empujan la pieza **contra** los apoyos, nunca en contra de ellos. Si un amarre deforma la pieza, la referencia está mal elegida.

## Cómo llega un trabajo a la OT

1. Solicitud de Producción o de un cliente (correo o parte en el ERP).
2. Análisis de viabilidad: plano, material, cadencia, si la soldadura es manual o robotizada.
3. Diseño (instrucción IT-051 para utillajes de soldadura).
4. Revisión de diseño por una persona de nivel técnico o superior.
5. Fabricación interna o externa.
6. Validación con primera serie e informe dimensional de Calidad.

## Tu itinerario de las primeras semanas

| Semana | Objetivo | Evidencia |
|---|---|---|
| 1 | Conocer la planta, el PDM y la codificación | Recorrido con Producción; alta en el PDM |
| 2 | Revisar planos de cliente acompañado (IT-052) | Dos revisiones comentadas por tu tutora |
| 3 | Diseñar un utillaje sencillo con la plantilla UT-PLANTILLA-03 | Modelo y planos en borrador |
| 4 | Presentar el diseño en la revisión semanal de los jueves | Lista de comprobación de revisión firmada |

## Glosario

- **Utillaje**: útil que posiciona y sujeta la pieza durante una operación (soldadura, control, mecanizado).
- **Amarre**: elemento que sujeta la pieza contra los apoyos (gato de palanca, cilindro neumático).
- **Poka-yoke**: detalle de diseño que impide colocar la pieza mal.
- **Primera serie**: las cinco primeras piezas fabricadas con un utillaje nuevo, que se miden completas.
"""

PROC_UTILLAJES = f"""# Procedimiento de diseño de utillajes (PR-OT-02, revisión B)

{AVISO}

## 1. Objeto y alcance

Este procedimiento fija cómo se diseñan, revisan y validan los utillajes de soldadura y de control de Metalúrgica Arlanza. Aplica a todos los utillajes nuevos y a las modificaciones que cambien referencias o amarres.

## 2. Responsabilidades

| Quién | Responsabilidad |
|---|---|
| Diseñador (nivel 1 o superior) | Diseña según este procedimiento y la instrucción IT-051 |
| Revisor (nivel 2 o superior) | Revisa el diseño con la lista de comprobación del apartado 6 |
| Responsable de OT | Aprueba el diseño y la fabricación |
| Calidad | Mide la primera serie y emite el informe dimensional |

## 3. Datos de entrada obligatorios

- Plano de la pieza en revisión liberada y modelo 3D.
- Secuencia de soldadura y tipo de proceso (MAG manual o robotizado en la célula R2).
- Cadencia prevista (piezas por hora) y vida estimada del utillaje (piezas totales).
- Cotas críticas y características especiales marcadas por el cliente.

## 4. Criterios de diseño

### 4.1 Referencias y apoyos

- Sistema 3-2-1 sobre las superficies que el plano usa como referencia de cotas.
- Apoyos intercambiables, en acero templado (dureza mínima 55 HRC) cuando haya desgaste.
- Holgura entre pieza y topes laterales de **0,2 a 0,5 mm** para absorber la dilatación al soldar.

### 4.2 Amarres

- Preferencia por gatos de palanca normalizados de la biblioteca; neumáticos si la cadencia supera 30 piezas por hora.
- La fuerza del amarre se dimensiona con un coeficiente de seguridad de 2 sobre la necesaria para vencer la deformación de soldadura.
- Ningún amarre puede quedar en la trayectoria de la antorcha ni del operario.

### 4.3 Soldadura

- Accesibilidad de la antorcha: ángulo de trabajo de **45° ± 15°** y distancia libre mínima de 15 mm alrededor de la boquilla.
- Las zonas próximas al cordón llevan placas de cobre o acero inoxidable para evitar que se pegue la proyección.
- Toma de masa en el propio utillaje, lo más cerca posible de los cordones.

### 4.4 Ergonomía y seguridad

- Altura de trabajo entre **900 y 1.100 mm**.
- Peso de cada parte desmontable: máximo 15 kg; si pasa de ese peso, puntos de elevación.
- Aristas matadas y sin puntos de atrapamiento en el cierre de los amarres.

### 4.5 Poka-yoke e identificación

- La pieza no puede colocarse girada: un tope asimétrico o un pasador lo impide.
- Placa grabada con código UT-AAAA-NNN, referencia de la pieza y fecha de validación.

## 5. Documentación del diseño

Planos de conjunto y de despiece con la plantilla UT-PLANTILLA-03, lista de materiales con componentes normalizados, hoja de mantenimiento del utillaje (piezas de desgaste y frecuencia de revisión) y fotografía del utillaje terminado.

## 6. Revisión de diseño

| Punto de la lista | Criterio de aceptación |
|---|---|
| Referencias | Coinciden con las referencias de cotas del plano de la pieza |
| Holguras | Entre 0,2 y 0,5 mm en topes laterales |
| Antorcha | Simulación sin colisiones en todos los cordones |
| Amarres | Fuera de la trayectoria de la antorcha; fuerza justificada |
| Ergonomía | Altura y pesos dentro de los límites del apartado 4.4 |
| Poka-yoke | Imposible colocar la pieza girada |
| Documentación | Planos, lista de materiales y hoja de mantenimiento completos |

## 7. Validación

Se fabrican cinco piezas con el utillaje nuevo. Calidad mide todas las cotas críticas y emite el informe dimensional. El utillaje se libera si las cinco piezas cumplen y la capacidad preliminar de las cotas críticas es Cpk ≥ 1,33. Si no cumple, se analiza la causa con el diseñador y se registra la modificación con nueva revisión de plano.
"""

COSTES = f"""# Costes y proveedores de utillaje

{AVISO}

Documento de uso interno de la responsable de Oficina técnica y de dirección. Recoge los proveedores homologados, los precios de referencia y las reglas de aprobación de compras de utillaje.

## Proveedores homologados (ficticios)

| Proveedor | Especialidad | Plazo habitual | Valoración 2025 |
|---|---|---|---|
| Talleres Valdearlanza | Utillajes de soldadura manuales y estructuras | 3 a 4 semanas | A (sin incidencias) |
| Mecanizados Cerezo Norte | Apoyos templados, rectificado y piezas de precisión | 2 a 3 semanas | A |
| Utillajes Páramo | Utillajes neumáticos y para célula robotizada | 5 a 6 semanas | B (un retraso en el UT-2025-009) |
| Neumática Carrión Sistemas | Cilindros, válvulas y montaje neumático | 1 a 2 semanas | A |

## Precios de referencia

| Concepto | Precio de referencia |
|---|---|
| Hora de diseño interno (coste cargado) | 48 €/h |
| Hora de mecanizado convencional en proveedor | 42 a 50 €/h |
| Hora de rectificado | 55 €/h |
| Estructura soldada en acero S355 (con mecanizado de base) | 9 a 12 €/kg |
| Gato de palanca normalizado | 35 a 90 € la unidad |
| Cilindro neumático con detector | 180 a 320 € la unidad |

## Coste típico por tipo de utillaje

| Tipo | Rango de coste | Ejemplo |
|---|---|---|
| Utillaje manual sencillo (hasta 6 amarres) | 1.200 a 2.500 € | UT-2025-014, soportes SL-12: 1.860 € |
| Utillaje manual complejo | 2.500 a 4.500 € | UT-2024-031, bastidor BT-40: 3.950 € |
| Utillaje neumático | 4.000 a 9.000 € | UT-2025-009, colector CL-200: 7.400 € |
| Utillaje para célula robotizada | 9.000 a 18.000 € | UT-2025-021, chasis CH-7: 15.200 € |

## Aprobación de compras de utillaje

- Hasta **3.000 €**: aprueba la responsable de Oficina técnica.
- De **3.000 a 12.000 €**: aprueba la dirección técnica, con dos ofertas comparadas.
- Más de **12.000 €**: aprueba la gerencia, con tres ofertas y el cálculo de amortización.

Toda compra de utillaje lleva el número de proyecto y la referencia del cliente para poder repercutir el coste.

## Cálculo de amortización por pieza

Coste por pieza = (coste del utillaje + coste de mantenimiento previsto) / piezas previstas en la vida del proyecto. Como regla, el utillaje no debe superar el 4 % del precio de venta de la pieza durante los dos primeros años. Si lo supera, se plantea al cliente el pago del utillaje por separado.

## Criterios para elegir proveedor

1. Plazo compatible con la fecha de arranque del cliente.
2. Experiencia demostrada en utillajes parecidos (pedir fotos de trabajos anteriores).
3. Precio, comparando siempre ofertas sobre el mismo plano y la misma lista de materiales.
4. Capacidad de respuesta para modificaciones durante la validación.
"""

LINEA2 = f"""# Instrucción de montaje de la línea 2

{AVISO}

## 1. Descripción de la línea

La línea 2 monta el **colector CL-200** para equipos de climatización. Trabaja a dos turnos con un tiempo de ciclo objetivo de **90 segundos** por conjunto y seis estaciones en serie:

| Estación | Operación | Instrucción | Herramienta principal |
|---|---|---|---|
| E1 | Preparación y limpieza del colector | IT-021 | Paño sin pelusa y desengrasante |
| E2 | Montaje de la brida B | IT-023 | Llave dinamométrica de 1/2" |
| E3 | Montaje de soportes laterales SL-12 | IT-024 | Atornillador de embrague |
| E4 | Prueba de estanqueidad | Banco BE-2 | Banco automático a 3 bar |
| E5 | Inspección final y etiquetado | IT-026 | Plantilla visual y etiquetas |
| E6 | Embalaje | IT-025 | Enfardadora |

## 2. Pares de apriete de la línea

| Unión | Tornillería | Par | Secuencia |
|---|---|---|---|
| Brida B sobre colector | 4 × M10 × 40, calidad 8.8 | 25 N·m | En cruz, dos pasadas (12 y 25 N·m) |
| Soporte lateral SL-12 | 2 × M8 × 20 | 18 N·m | Primero el tornillo superior |
| Abrazadera del manguito | Tornillo sin fin | 4 N·m | Una pasada |

Las llaves dinamométricas se verifican cada 6 meses en el laboratorio. Si la etiqueta de verificación está caducada, no uses la llave y avisa a tu responsable.

## 3. Materiales y consumibles

- Brida B: referencia **BR-B-080**, en carros de 40 unidades.
- Junta de EPDM: referencia **JT-80**, en cajas de 200. La junta no se reutiliza nunca.
- Tornillería M10 × 40 8.8 cincada y arandelas planas, en cajetines de la estación E2.
- Etiqueta verde «OK estanqueidad» y etiqueta roja de no conforme, en el lateral de la estación E5.

## 4. Arranque de la línea al inicio del turno

1. Comprueba el orden y la limpieza de cada estación y que no quedan piezas del turno anterior sin identificar.
2. Verifica las etiquetas de las llaves dinamométricas y del banco BE-2.
3. Haz el ciclo de autoverificación del banco BE-2 con la pieza patrón (debe dar OK).
4. Fabrica el primer conjunto y entrégalo a Calidad para el control de primera pieza. No sigas hasta tener el OK.

## 5. Qué hacer si algo va mal

- **Conjunto que no supera la estanqueidad**: etiqueta roja, al contenedor rojo de la estación E5 y aviso al responsable de turno. Nunca se reprocesa en la línea.
- **Falta de material**: tira del andon amarillo; el logístico repone en menos de 10 minutos.
- **Avería o riesgo**: andon rojo y parada de la estación. Avisa a Mantenimiento por la extensión 230.

## 6. Registro

Cada conjunto lleva un número de serie. La estación E5 lo registra con su resultado de estanqueidad. En la pantalla de cada estación se ve la instrucción vigente y se puede preguntar a CidIA en el contexto del paso.
"""

PREVENTIVO = f"""# Plan de mantenimiento preventivo de prensas

{AVISO}

## 1. Alcance

Prensas de la nave 1: P1 (250 t, mecánica), P2 (400 t, hidráulica), P3 (630 t, hidráulica, con cambio rápido de molde) y P4 (160 t, mecánica). Las órdenes de trabajo se generan en el GMAO y se cierran con la firma de quien las hace.

Antes de cualquier tarea de este plan con la máquina abierta o con riesgo de movimiento, se **consigna** la prensa (procedimiento de consignación e instrucción IT-073 para la P3).

## 2. Tareas diarias (operario de prensa, al inicio del turno)

| Tarea | Prensas | Criterio |
|---|---|---|
| Comprobar nivel de aceite hidráulico en el visor | P2, P3 | Entre las marcas de mínimo y máximo |
| Revisar fugas visibles en racores y latiguillos | Todas | Sin goteo; si hay goteo, aviso a Mantenimiento |
| Probar la barrera fotoeléctrica con la varilla de prueba | Todas | La prensa se detiene en cualquier punto de la barrera |
| Comprobar los pulsadores de parada de emergencia | Todas | La prensa se detiene y no rearma sola |
| Limpiar virutas y recortes de la mesa | Todas | Mesa limpia antes del primer golpe |

## 3. Tareas semanales (Mantenimiento)

| Tarea | Prensas | Detalle |
|---|---|---|
| Engrase de guías del carro (IT-072) | Todas | Grasa EP-2 en los 8 engrasadores; la P3 cada **40 horas** de trabajo |
| Limpieza del sensor S4 de presencia de pieza | P3 | Aire a baja presión (máximo 2 bar), sin disolventes |
| Revisión de los amarres hidráulicos de molde | P3 | Sin fugas; presión de amarre en verde (180 bar) |
| Tensión de correas del volante | P1, P4 | Flecha de 10 a 12 mm |

## 4. Tareas mensuales

| Tarea | Prensas | Detalle |
|---|---|---|
| Calibración del sensor S4 (IT-071) | P3 | Distancia de detección 8 mm ± 0,5 mm con la pieza patrón PT-S4 |
| Verificación del ángulo de parada | P1, P4 | Ángulo de parada inferior a 10° con el registrador |
| Limpieza de filtros de aire de los cuadros | Todas | Cambio si están colmatados |
| Revisión de la plataforma de acceso y la escalera | P3 | Barandillas firmes, peldaños sin aceite |

## 5. Tareas anuales

- Cambio de aceite hidráulico y filtros de retorno y presión (P2 y P3), o cada **4.000 horas** si se alcanza antes.
- Revisión de la estructura y de las uniones atornilladas del cabezal.
- Inspección reglamentaria de la función de seguridad (barreras, mandos a dos manos, válvulas de seguridad) por organismo de control.
- Termografía de los cuadros eléctricos (IT-075 e IT-076).

## 6. Indicadores

| Indicador | Objetivo 2026 |
|---|---|
| Cumplimiento del preventivo | ≥ 95 % de órdenes cerradas en plazo |
| Tiempo medio entre averías de la P3 | ≥ 120 horas |
| Tiempo medio de reparación | ≤ 45 minutos |
| Paradas por atasco al cambiar de molde (P3) | Reducir un 50 % respecto a 2025 |
"""

CONTROL_CALIDAD = f"""# Plan de control de calidad del colector CL-200 (PC-CAL-01)

{AVISO}

## 1. Alcance

Características que se controlan en el colector CL-200 y en sus componentes estampados, desde la recepción de material hasta la expedición. Responsable del plan: **Elena Moreno** (Calidad).

## 2. Características y frecuencias

| Característica | Especificación | Método | Frecuencia | Reacción si no cumple |
|---|---|---|---|---|
| Diámetro interior de la brida B | 80,0 ± 0,2 mm | Calibre digital (IT-061) | Primera pieza y 1 de cada 50 | Parar, segregar el lote desde el último control OK |
| Planitud de la cara de asiento | ≤ 0,1 mm | Mármol y galgas | Primera pieza y 1 por turno | Parar y avisar a Calidad |
| Par de apriete de la brida B | 25 N·m ± 10 % | Llave de verificación | 1 de cada 100 conjuntos | Revisar llave y conjuntos desde el último control |
| Estanqueidad | Caída ≤ 0,05 bar en 60 s a 3 bar | Banco BE-2 | 100 % | Etiqueta roja y contenedor de no conforme |
| Posición de los taladros del soporte SL-12 | ± 0,3 mm | Calibre pasa/no pasa | Primera pieza y 1 de cada 100 | Revisar utillaje UT-2025-014 |
| Aspecto del cordón de soldadura | Sin poros ni mordeduras visibles | Visual con patrón | 100 % | Reparación según IT-041 o rechazo |

## 3. Control de primera pieza

Se hace tras cada cambio de molde, cambio de turno, cambio de lote de material o intervención de Mantenimiento en la máquina (IT-065). La primera pieza se mide completa y se compara con la hoja de control. Hasta que Calidad da el OK, la producción no sigue. La pieza medida se guarda identificada hasta el final del turno.

## 4. Equipos de medida

| Equipo | Frecuencia de calibración | Responsable |
|---|---|---|
| Calibres digitales de 150 mm | Cada 12 meses (externa) y verificación interna mensual con bloques patrón | Laboratorio |
| Micrómetros de exteriores | Cada 12 meses | Laboratorio |
| Llaves dinamométricas | Cada 6 meses en banco de par (IT-063); tolerancia ± 4 % | Laboratorio |
| Banco de estanqueidad BE-2 | Autoverificación diaria y calibración anual | Calidad y Mantenimiento |

Un equipo con la etiqueta de calibración caducada **no se usa**: se retira al laboratorio.

## 5. Control estadístico

Las cotas críticas (diámetro de la brida B y planitud) se registran en gráficos de control por turno. Se reacciona ante un punto fuera de límites, siete puntos seguidos al mismo lado de la media o una tendencia de seis puntos. Objetivo de capacidad: Cpk ≥ 1,33.

## 6. Producto no conforme

1. Identifica la pieza con etiqueta roja y anota el defecto.
2. Llévala a la zona de no conforme (jaula roja) de la nave.
3. Registra la no conformidad en el ERP con cantidad, lote y defecto.
4. Calidad decide: reproceso con instrucción aprobada, uso con concesión del cliente o achatarrado.

## 7. Auditoría de producto

Cada semana Calidad audita cinco conjuntos al azar del almacén de expedición contra este plan. Los resultados se revisan en la reunión de calidad de los lunes.
"""

GUIA_CALIDAD = f"""# Guía de iniciación a Calidad

{AVISO}

## Para qué está Calidad

Calidad asegura que lo que sale de la planta cumple lo que el cliente ha pedido, y que cuando algo falla se sabe por qué y no se repite. Trabaja en el laboratorio metrológico y en la propia línea.

## Leer una cota con tolerancia

Una cota «80,0 ± 0,2» significa que la pieza es buena si mide entre **79,8 y 80,2 mm**. Si no se indica tolerancia, se aplica la tolerancia general del plano (en nuestros planos, ISO 2768-mK).

## El calibre digital, paso a paso

1. Comprueba que la etiqueta de calibración está vigente.
2. Limpia las palas y ciérralas: la pantalla debe marcar 0,00. Si no, pulsa cero.
3. Coloca la pieza entre las palas sin forzar, perpendicular a la cota.
4. Lee el valor y repite la medida tres veces; anota la media.
5. Vuelve a guardar el calibre en su estuche.

Errores típicos: medir con la pieza caliente recién salida de soldadura (déjala atemperar), medir torcido, apretar demasiado las palas o medir sobre una rebaba.

## Etiquetas y colores

| Color | Significado |
|---|---|
| Verde | Pieza o lote conforme, liberado |
| Amarillo | Pendiente de decisión de Calidad: no se usa |
| Rojo | No conforme: a la zona de no conforme |

## Qué hacer cuando encuentras un defecto

Para la producción si el defecto puede repetirse, separa lo sospechoso desde el último control bueno, avisa al responsable de turno y registra la no conformidad. Si el defecto es recurrente se abre un análisis 8D: equipo, descripción, contención, causa raíz, acción correctiva, verificación, prevención y cierre.

## Primeras semanas

| Semana | Objetivo |
|---|---|
| 1 | Plan de control del CL-200 y medición con calibre (IT-061) |
| 2 | Control de primera pieza acompañado (IT-065) |
| 3 | Gestión de producto no conforme (IT-066) y registro en el ERP |
"""

CONSIGNACION = f"""# Procedimiento de consignación de máquinas

{AVISO}

## 1. Para qué sirve

Consignar es dejar una máquina **sin ninguna energía peligrosa** y asegurar que nadie la puede volver a poner en marcha mientras alguien trabaja en ella. Se hace antes de limpiar, ajustar, reparar, cambiar molde o despejar un atasco dentro de la zona de peligro.

## 2. Energías que hay que controlar en una prensa

| Energía | Cómo se aísla | Cómo se comprueba |
|---|---|---|
| Eléctrica | Seccionador general en OFF con candado | Intentar el arranque: no debe responder |
| Hidráulica | Bomba parada y descarga del acumulador | Manómetro de la central a cero |
| Neumática | Válvula de corte con candado y purga de la línea | Manómetro de la entrada a cero |
| Gravedad (carro en alto) | Carro abajo o calzos de seguridad | Calzos colocados y visibles |

## 3. Los seis pasos

1. **Avisa** al responsable y a las personas de la zona.
2. **Para** la máquina con el mando normal (carro en el punto muerto superior en las prensas).
3. **Aísla** todas las energías de la tabla anterior.
4. **Bloquea** cada punto de aislamiento con tu candado personal y tu tarjeta con nombre y fecha.
5. **Comprueba** la energía cero: pulsa marcha, mira los manómetros, comprueba que nada se mueve.
6. **Trabaja**. Al terminar, retira herramientas, recoloca resguardos, avisa y retira tu candado. Solo quien puso el candado lo quita.

## 4. Reglas que no se discuten

- Un candado, una persona, una llave. Si trabajáis varios, cada uno pone el suyo.
- Nunca quites el candado de otra persona. Si alguien se ha ido dejando su candado, avisa a tu responsable: hay un procedimiento de retirada con testigos.
- Una tarjeta sin candado no es una consignación.

## 5. Prensa 3: puntos de aislamiento

Seccionador general Q0 del armario A1, válvula de corte neumático V-N1 junto a la escalera, descarga del acumulador con la llave de bola KB-3 y calzos amarillos en el soporte de la columna derecha. La instrucción IT-073 detalla el orden.
"""

MANUAL_P3 = f"""# Manual de manejo de la prensa 3 (extracto)

{AVISO}

## 1. Datos principales

| Característica | Valor |
|---|---|
| Tipo | Prensa hidráulica de doble montante |
| Fuerza nominal | 630 t |
| Mesa | 2.500 × 1.400 mm |
| Altura de cierre | 350 a 650 mm (ajustable por receta) |
| Golpes por minuto en automático | Hasta 18 |
| Amarres de molde | Hidráulicos, 4 en carro y 4 en mesa; presión de amarre 180 bar |
| Cambio de molde | Carro de cambio rápido con rodillos y tacos de centrado |
| Sensor S4 | Inductivo M18, presencia de pieza en el molde; distancia de detección 8 mm |

## 2. Modos de trabajo

- **Manual**: golpe a golpe con mando a dos manos. Se usa para ajustes y para la prueba tras el cambio de molde.
- **Lento**: velocidad reducida para comprobar el cierre del molde.
- **Automático**: ciclo continuo con alimentación desde el enderezador; requiere resguardos cerrados y sensor S4 activo.

## 3. Recetas de molde

Cada molde tiene una receta en el panel con su altura de cierre, velocidades y presiones de trabajo. El código de receta está grabado en la placa del molde (por ejemplo, M-318 para el soporte SL-12, altura de cierre 412,5 mm). No se cambian los parámetros de una receta sin autorización de Oficina técnica.

## 4. Alarmas más frecuentes

| Alarma | Significado | Qué hacer |
|---|---|---|
| A12 · Falta pieza S4 | El sensor S4 no detecta pieza en el molde | Comprobar alimentación; si hay pieza, limpiar S4 |
| A17 · Amarre sin presión | Uno de los amarres no llega a 180 bar | No golpear; avisar a Mantenimiento |
| A21 · Barrera interrumpida | La barrera fotoeléctrica se ha cortado | Retirar el obstáculo y rearmar |
| A30 · Sobrecarga | Se ha superado la fuerza máxima del molde | Parar y avisar al responsable de turno |

## 5. Al terminar el turno

Carro en el punto superior, modo manual, mesa limpia y anotación en el parte de turno de las incidencias y de los golpes realizados.
"""

ACOGIDA_PROD = f"""# Guía de acogida en Producción

{AVISO}

## Cómo está organizada Producción

Producción tiene tres puestos: **Prensas** (nave 1), **Montaje línea 2** (nave 2) y **Soldadura** (nave 2). Responsable del departamento: **Javier Martín**. Persona experta en montaje: **Carmen Díaz**.

## Lo primero que tienes que saber

- Cada puesto tiene su pantalla con la instrucción vigente. Síguela paso a paso en el modo planta de CidIA: los pasos críticos piden confirmación.
- Si dudas, pregunta. A CidIA en el propio paso, o a la persona experta del puesto. Preguntar no penaliza: tu progreso mide lo que vas dejando de necesitar preguntar.
- La primera pieza tras un cambio siempre va a Calidad antes de seguir.

## Instrucciones del itinerario de Producción

| Código | Tarea | Puesto | Criticidad |
|---|---|---|---|
| IT-023 | Montaje de la brida B | Montaje línea 2 | Alta |
| IT-024 | Montaje de soportes laterales | Montaje línea 2 | Media |
| IT-031 | Cambio de molde en la prensa 3 | Prensas | Alta |
| IT-032 | Arranque y parada segura de prensa | Prensas | Alta |
| IT-041 | Soldadura MAG de soportes | Soldadura | Media |

## Señales de la línea

| Andon | Significado |
|---|---|
| Verde | Todo en marcha |
| Amarillo | Falta material o hay una duda: acude el responsable de turno o el logístico |
| Rojo | Parada por avería o riesgo: acude Mantenimiento |

## Niveles de autonomía (ILUO)

- **I**: estás aprendiendo la tarea.
- **L**: la haces con ayuda; has superado el cuestionario y al menos tres ejecuciones.
- **U**: la haces sola o solo, con calidad; te ha observado un supervisor.
- **O**: puedes enseñarla a otras personas.
"""

DOCUMENTOS = [
    {"clave": "prl", "titulo": "Bienvenida y PRL", "fichero": "bienvenida-y-prl.md", "formato": "md",
     "departamento": None, "nivel": 1, "formacion": False, "publico": True, "autor": "admin",
     "subido_por": "admin", "dias": 41,
     "descripcion": "Acogida, distribución de la planta, normas de seguridad, emergencias y uso de CidIA.",
     "texto": BIENVENIDA},
    {"clave": "manual_ot", "titulo": "Manual de iniciación a Oficina técnica", "fichero": "manual-iniciacion-ot.md",
     "formato": "md", "departamento": "ot", "nivel": 1, "formacion": True, "publico": False, "autor": "ana",
     "subido_por": "ana", "dias": 40,
     "descripcion": "Funciones de la OT, codificación, tolerancias, sistema 3-2-1 e itinerario de las primeras semanas.",
     "texto": MANUAL_OT},
    {"clave": "diseno", "titulo": "Procedimiento de diseño de utillajes", "fichero": "PR-OT-02-diseno-utillajes.md",
     "formato": "md", "departamento": "ot", "nivel": 2, "formacion": False, "publico": False, "autor": "ana",
     "subido_por": "ana", "dias": 39,
     "descripcion": "PR-OT-02: criterios de diseño, revisión y validación de utillajes de soldadura y control.",
     "texto": PROC_UTILLAJES},
    {"clave": "costes", "titulo": "Costes y proveedores de utillaje", "fichero": "costes-proveedores-utillaje.md",
     "formato": "md", "departamento": "ot", "nivel": 3, "formacion": False, "publico": False, "autor": "ana",
     "subido_por": "ana", "dias": 38,
     "descripcion": "Proveedores homologados, precios de referencia y reglas de aprobación de compras.",
     "texto": COSTES},
    {"clave": "linea2", "titulo": "Instrucción de montaje de la línea 2", "fichero": "IT-L2-01-montaje-linea-2.pdf",
     "formato": "pdf", "departamento": "prod", "nivel": 1, "formacion": False, "publico": False, "autor": "carmen",
     "subido_por": "javier", "dias": 40, "cabecera": "IT-L2-01 · Instrucción de montaje de la línea 2 · Rev. C",
     "descripcion": "Estaciones de la línea 2, pares de apriete, consumibles, arranque y reacción ante fallos.",
     "texto": LINEA2},
    {"clave": "acogida_prod", "titulo": "Guía de acogida en Producción", "fichero": "guia-acogida-produccion.md",
     "formato": "md", "departamento": "prod", "nivel": 1, "formacion": True, "publico": False, "autor": "javier",
     "subido_por": "javier", "dias": 37,
     "descripcion": "Organización de Producción, itinerario de instrucciones, andon y niveles ILUO.",
     "texto": ACOGIDA_PROD},
    {"clave": "manual_p3", "titulo": "Manual de manejo de la prensa 3 (extracto)", "fichero": "manual-prensa-3.md",
     "formato": "md", "departamento": "prod", "nivel": 2, "formacion": False, "publico": False, "autor": "javier",
     "subido_por": "javier", "dias": 36,
     "descripcion": "Datos de la prensa P3, modos, recetas de molde y alarmas frecuentes.",
     "texto": MANUAL_P3},
    {"clave": "preventivo", "titulo": "Plan de mantenimiento preventivo de prensas",
     "fichero": "PM-PR-01-preventivo-prensas.pdf", "formato": "pdf", "departamento": "mant", "nivel": 1,
     "formacion": False, "publico": False, "autor": "jorge", "subido_por": "jorge", "dias": 39,
     "cabecera": "PM-PR-01 · Plan de mantenimiento preventivo de prensas · Rev. D",
     "descripcion": "Tareas diarias, semanales, mensuales y anuales de las prensas P1 a P4 e indicadores.",
     "texto": PREVENTIVO},
    {"clave": "consignacion", "titulo": "Procedimiento de consignación de máquinas",
     "fichero": "procedimiento-consignacion.md", "formato": "md", "departamento": "mant", "nivel": 1,
     "formacion": True, "publico": False, "autor": "jorge", "subido_por": "jorge", "dias": 39,
     "descripcion": "Los seis pasos de la consignación, energías de una prensa y puntos de aislamiento de la P3.",
     "texto": CONSIGNACION},
    {"clave": "control", "titulo": "Plan de control de calidad del colector CL-200",
     "fichero": "PC-CAL-01-plan-control-CL-200.md", "formato": "md", "departamento": "cal", "nivel": 2,
     "formacion": False, "publico": False, "autor": "elena", "subido_por": "elena", "dias": 38,
     "descripcion": "Características, frecuencias, equipos de medida, control estadístico y no conformes.",
     "texto": CONTROL_CALIDAD},
    {"clave": "guia_cal", "titulo": "Guía de iniciación a Calidad", "fichero": "guia-iniciacion-calidad.md",
     "formato": "md", "departamento": "cal", "nivel": 1, "formacion": True, "publico": False, "autor": "elena",
     "subido_por": "elena", "dias": 35,
     "descripcion": "Lectura de cotas, uso del calibre, etiquetas de colores y qué hacer ante un defecto.",
     "texto": GUIA_CALIDAD},
]
