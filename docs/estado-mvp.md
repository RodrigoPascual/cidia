# Estado del MVP de CidIA

Qué está hecho, dónde vive en el código y cómo se enseña, punto por punto del alcance de las bases. Se actualiza al cerrar cada fase.

Leyenda: **✓** funciona de punta a punta · **◐** funciona simplificado · **○** preparado, sin probar en el equipo real.

## 1. Captura y estructuración

| Punto de las bases | Estado | Cómo se demuestra | Código |
|---|---|---|---|
| Digitalización de procedimientos operativos | ✓ | Instrucciones de trabajo versionadas con pasos, críticos, seguridad, criterio de aceptación, imagen y clip | `servicios/instrucciones.py`, `paginas/instrucciones/` |
| Captura del conocimiento de operarios expertos | ✓ | Vídeo narrado, nota de voz, entrevista guiada y aportaciones desde la planta | `servicios/captura.py`, `servicios/aportaciones.py`, `paginas/captura/` |
| Generación automática de instrucciones | ✓ | Vídeo → transcripción con marcas de tiempo → escenas (scdet) → pasos propuestos por el LLM → imagen y clip por paso → borrador | `servicios/captura.py`, `servicios/video.py` |
| Documentación técnica convertida en formación | ✓ | Al publicar: micro-lecciones y cuestionario generados desde los pasos | `servicios/formacion.py`, `servicios/evaluacion.py` |
| Bases de conocimiento inteligentes | ✓ | Búsqueda híbrida (pgvector + texto en castellano + RRF) con permisos en SQL; WeKnora opcional | `conocimiento/pgvector.py`, `conocimiento/weknora.py` |
| Gestión centralizada del conocimiento | ✓ | Documentos con departamento, nivel mínimo, formación y público; consola «Probar búsqueda» | `rutas/documentos.py`, `paginas/documentos/` |

## 2. Formación en el puesto

| Punto | Estado | Cómo se demuestra | Código |
|---|---|---|---|
| Formación contextualizada en el puesto | ✓ | Modo planta con el copiloto en el contexto del paso | `servicios/planta.py`, `paginas/planta/` |
| Itinerarios personalizados | ✓ | Tareas del puesto y de las formaciones activas, con nivel ILUO y siguiente acción | `servicios/formacion.py`, `paginas/formacion/` |
| Micro-learning industrial | ✓ | Micro-lecciones con pregunta de control | `servicios/formacion.py` |
| Tutorización inteligente | ✓ | Modo socrático del copiloto | `servicios/consulta.py`, `ia/prompts.py` |
| Adaptado al perfil | ◐ | El itinerario y el contenido dependen del puesto, nivel y formación; la adaptación por nivel ILUO es por reglas | `servicios/progreso.py` |
| Acceso inmediato a contenidos | ✓ | Copiloto con citas, por texto o voz | `paginas/Copiloto.tsx` |

## 3. Acompañamiento

| Punto | Estado | Cómo se demuestra | Código |
|---|---|---|---|
| Asistencia guiada paso a paso | ✓ | Un paso por pantalla, letra y botones grandes, clip del experto | `paginas/planta/Ejecucion.tsx` |
| Apoyo a la toma de decisiones | ◐ | Respuestas citadas con documento, versión, paso, autor y validador | `servicios/consulta.py` |
| Recomendaciones según el contexto | ◐ | Siguiente acción del itinerario y respuestas en el contexto de la tarea | `servicios/formacion.py` |
| Validación de tareas realizadas | ✓ | Confirmación obligatoria de pasos críticos y foto final comparada con visión | `servicios/planta.py` |
| Seguimiento de progresos individuales | ✓ | Pasaporte de habilidades | `paginas/progreso/MiProgreso.tsx` |
| Necesidades formativas | ✓ | Lagunas agrupadas por similitud y frecuencia; consultas repetidas | `servicios/lagunas.py`, `paginas/aportaciones/Lagunas.tsx` |

## 4. Evaluación objetiva

| Punto | Estado | Cómo se demuestra | Código |
|---|---|---|---|
| Evaluación continua | ✓ | Curva de autonomía: consultas por ejecución | `servicios/progreso.py` |
| Seguimiento de hitos | ✓ | Niveles ILUO con evidencias y fechas | `servicios/iluo.py` |
| Registro de actividades | ✓ | Sentencias xAPI en PostgreSQL, visor y exportación | `xapi.py`, `rutas/admin_registro.py` |
| Trazabilidad hasta versión y autor | ✓ | Cada cita y cada evaluación apuntan a la versión de la instrucción | `modelos.py` |
| Indicadores de desempeño | ✓ | Panel de equipo: personas en L o más, caducidades, reevaluaciones | `paginas/progreso/Equipo.tsx` |
| Validación (cuestionario y observación) | ✓ | Cuestionario aprobado por el experto; observación del supervisor con lista de comprobación | `servicios/evaluacion.py` |

## 5. Certificación

| Punto | Estado | Cómo se demuestra | Código |
|---|---|---|---|
| Evidencias de competencia | ✓ | Evidencias guardadas en cada nivel ILUO | `servicios/iluo.py` |
| Pasaporte digital de habilidades | ✓ | Panel de progreso por persona, equipo y planta | `paginas/progreso/` |
| Certificación por puesto o tarea | ✓ | Nivel ILUO por tarea con reglas configurables | `servicios/iluo.py` |
| Gestión de niveles | ✓ | Reglas ajustables en Administración; ajuste manual con motivo y auditoría | `rutas/admin.py` |
| Renovación y actualización | ✓ | Caducidad por nivel y reevaluación al publicar una versión nueva | `servicios/iluo.py` |
| Auditoría y trazabilidad | ✓ | Auditoría de cambios de administración y xAPI | `xapi.py` |

## 6. Requisitos generales

| Requisito | Estado | Detalle |
|---|---|---|
| Base tecnológica e IA relevante | ✓ | LLM local con visión, embeddings, voz, RAG con citas, agente con MCP |
| Aplicable en entorno real | ○ | Probado con datos sintéticos en el servidor de pruebas; el piloto con empresa queda para la fase siguiente |
| Escalabilidad | ◐ | Gateway sin estado, MCP sin sesión, perfiles de servidor; la demo va en un equipo |
| Integración | ◐ | xAPI exportable, módulo de identidad con conectores LDAP y OIDC preparados, API OpenAI y MCP |
| Implantación sencilla y económica | ✓ | `instalar-servidor.sh` para el servidor y `CidIA-Setup.exe` para los portátiles; todo libre y en local |

## 7. Piezas

| Pieza | Estado | Notas |
|---|---|---|
| Gateway (API, OpenAI, MCP) | ✓ | 1.069 pruebas automáticas en verde (`servidor/gateway/qa/pruebas_en_paralelo.sh`), incluida una batería de seguridad que recorre todas las rutas con cada rol |
| Interfaz web | ✓ | Servida en `/app/`; embebida en la app de escritorio. Revisada pantalla a pantalla con cada rol en escritorio, portátil, móvil y modo embebido, sin errores de consola |
| App de escritorio y `CidIA-Setup.exe` | ✓ | Instalada y verificada de punta a punta en el PC de desarrollo (sesión, secciones por permisos, MCP, micrófono por el puente del plugin, sin conexiones externas); ver `app/README.md` |
| Instalador del servidor y herramienta `cidia` | ○ | Probado en modo comprobación en el servidor de pruebas; la instalación desde cero será en el MSI (`docs/manual-servidor.md`) |
| Servidor de pruebas Oracle (ARM) | ✓ | Modelos diminutos; sirve para validar flujos, no rendimiento |
| MSI con Ubuntu y GPU | ○ | Perfil `msi` listo (Ministral 3 8B); pendiente de instalar |

## 8. Límites conocidos

* La app de escritorio parte de DeepSeek Harness sin recompilar: los menús nativos, algunos diálogos y el instalador base siguen en inglés; la política de actualización obligatoria de la app base no se puede desactivar por configuración (bloquear su dominio en la red de la empresa). El rebrand compilado es de la fase 4.
* Con los modelos diminutos del servidor de pruebas las respuestas son pobres: la calidad real se mide en el MSI.
* El motor WeKnora no forma parte del despliegue por defecto por licencias (su lector de documentos incluye EbookLib, AGPL); el motor propio cubre la búsqueda híbrida en castellano.

## 9. Documentos de apoyo

* `docs/guia-demo.md`: demostración de 3 minutos con plan B por paso; `datos-demo/README.md`: quién es quién en los datos sintéticos.
* `docs/manual-servidor.md`: instalación del servidor (MSI o equipo de empresa) y herramienta `cidia` (incluido el modo demo).
* `docs/presupuesto-hardware.md`: presupuesto con precios consultados el 10 de octubre de 2026 por perfil de empresa.
* `docs/prueba-audio-ruido.md`: transcripción con ruido industrial (propuesta C7).
* `docs/plantillas/`: aviso a las personas trabajadoras y consentimiento de imagen y voz (borradores para revisar con la empresa).
* `THIRD_PARTY_NOTICES.md`: licencias de todo lo que usa CidIA.
