# Empresa modelo: Metalúrgica Arlanza, S. L.

Ficha de dimensionamiento de una pyme industrial tipo, preparada con una persona del sector para comprobar que CidIA encaja en una planta real. Los datos de demostración del repositorio (`datos-demo/` y la semilla del servidor) son una muestra sintética y reducida de esta empresa.

## Perfil

* **Sector**: fabricación de componentes metálicos y subconjuntos industriales.
* **Plantilla**: 65 personas (45 en planta y taller, 20 en oficinas y gestión).
* **Turnos**: dos turnos de producción (mañana y tarde).

## Estructura y perfiles en CidIA

| Departamento | Personas | Perfiles clave |
|---|---|---|
| Producción y taller | 38 | 1 jefe de planta, 2 encargados de turno, 5 operarios sénior o expertos, 30 operarios de línea y prensas |
| Oficina técnica y calidad | 10 | 1 responsable de calidad, 3 ingenieros de procesos, 6 técnicos de verificación y metrología |
| Mantenimiento | 6 | 1 responsable, 5 técnicos electromecánicos |
| Logística y almacén | 6 | 1 responsable, 5 carretilleros y mozos de almacén |
| Dirección, RR. HH. y PRL | 5 | 1 gerente, 2 de administración y finanzas, 2 de RR. HH. y prevención |

## Volumen de conocimiento

| Tipo | Volumen | Cómo entra en CidIA |
|---|---|---|
| Instrucciones técnicas de trabajo (hojas de proceso, gamas, pautas de apriete, cambios de molde) | más de 120 | Documentos y captura desde vídeo; versiones v1, v2… con reevaluación |
| Manuales de maquinaria (prensas, CNC, líneas de ensamblaje, esquemas) | más de 35 | Documentos con permisos por departamento |
| Fichas de seguridad y PRL (EPI por puesto, LOTO, productos químicos) | más de 40 | Documentos públicos para toda la plantilla y pasos críticos en las instrucciones |
| Procedimientos de calidad ISO 9001 | más de 25 | Documentos de oficina técnica y calidad |
| Conocimiento tácito de los veteranos (trucos de ajuste, atascos habituales) | más de 50 micro-lecciones | Notas de voz, entrevistas guiadas y aportaciones validadas |

## Roles y permisos

* **Administración y oficina técnica**: aprueban procedimientos, suben manuales y gestionan versiones.
* **Supervisores y mandos intermedios**: matriz ILUO, observaciones en el puesto y lagunas de conocimiento de su turno.
* **Operarios de planta**: solo los procedimientos e instrucciones de su departamento y puesto, más lo que estén aprendiendo.

## Implantación y gestión del cambio

* La captura se presenta como un **reconocimiento al experto veterano**: su forma de trabajar queda firmada y versionada en la instrucción.
* El uso del copiloto es **voluntario y de apoyo**: la curva de autonomía muestra cómo cada persona necesita cada vez menos consultas.
* Las métricas de CidIA (tiempo hasta la autonomía, consultas en pasos críticos, instrucciones al día) se pueden leer junto a los indicadores de planta (OEE, rechazos, paradas) para hablar con dirección en términos de retorno.

## Vídeos reales para probar la captura

Tutoriales públicos de taller con buena locución en castellano, útiles para probar la extracción de pasos y puntos críticos (solo para pruebas internas; para una demostración pública hace falta permiso del autor o licencia libre):

* Cambio rápido de molde con SMED: sujeción rápida, conectores múltiples y cambio de herramientas.
* Uso de una prensa hidráulica con molde metálico: componentes, carga, presurización, extracción y limpieza.
* Bloqueo y etiquetado LOTO paso a paso: fuentes de energía, candados, verificación de energía cero y desbloqueo.
* Ajuste y montaje de moldes de inyección: alineación de platos, unidad de cierre y purga de refrigeración.
