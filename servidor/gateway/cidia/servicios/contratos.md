# Contratos entre servicios

Funciones que unos dominios llaman en otros. La firma no se cambia sin avisar; el cuerpo lo
implementa el dueño del módulo. Todas reciben la sesión de BD y **no hacen commit** salvo
que se diga lo contrario (lo hace quien llama).

## servicios/documentos.py (hecho)
* `crear_desde_subida(bd, actor, subida, titulo, departamento_id, nivel_minimo, es_formacion, es_publico, descripcion) -> Documento` (hace commit y encola el indexado).
* `crear_desde_texto(bd, titulo, texto, tipo, departamento_id, nivel_minimo, es_formacion, es_publico, autor_id, validador_id, subido_por_id, origen, origen_id, version, partes, en_segundo_plano, descripcion) -> Documento`. Con `en_segundo_plano=True` hace commit y encola.
* `indexar(bd, doc, partes=None)`, `reindexar(bd, doc)`, `borrar(bd, doc)`, `a_dict(bd, doc)`.

## servicios/consulta.py
* `buscar(bd, actor, pregunta, k=None) -> list[Encontrado]`: búsqueda con el alcance del actor.
* `async responder_stream(bd, actor, pregunta, modo="normal", contexto=None, historial=None) -> AsyncIterator[dict]`: eventos `{"tipo": "fuentes", "fuentes": [...]}`, `{"tipo": "token", "texto": "..."}`, `{"tipo": "fin", "consulta_id": int, "con_respaldo": bool, "laguna_id": int|None}`, `{"tipo": "error", "mensaje": "..."}`. `contexto` = `{"tarea_id", "paso_id", "ejecucion_id"}`.
* `responder(bd, actor, pregunta, modo="normal", contexto=None, historial=None) -> dict`: igual pero sin streaming (`{"respuesta", "fuentes", "con_respaldo", "consulta_id", "laguna_id"}`).

## servicios/lagunas.py
* `registrar(bd, pregunta, departamento_id, tarea_id=None) -> Laguna`: agrupa con una existente si la pregunta es parecida (similitud de embeddings >= 0.85) e incrementa su frecuencia.
* `resolver(bd, laguna_id, aportacion_id) -> None`.

## servicios/iluo.py
* `recalcular(bd, usuario_id, tarea_id) -> NivelIluo`: aplica las reglas de docs/arquitectura.md §7 con la configuración de `empresa.config_iluo`, registra xAPI `certifico` si sube de nivel.
* `marcar_reevaluacion(bd, tarea_id) -> int`: al publicar una nueva versión; devuelve cuántas personas quedan marcadas.
* `validar_formador(bd, actor, usuario_id, tarea_id) -> NivelIluo`.
* `nivel_letra(n) -> str` ("", "I", "L", "U", "O").

## servicios/formacion.py
* `generar_microlecciones(bd, instruccion_id) -> int` (trabajo en segundo plano: `encolar_generacion(instruccion_id)`).
* `itinerario(bd, actor) -> list[dict]`.

## servicios/evaluacion.py
* `generar_preguntas(bd, instruccion_id, n=6) -> int` (y `encolar_generacion(instruccion_id)`).

## servicios/instrucciones.py
* `publicar(bd, actor, instruccion_id) -> Instruccion`: marca obsoleta la anterior, indexa con `documentos.crear_desde_texto` (tipo `instruccion`, un elemento de `partes` por paso con metadatos `{"paso": orden, "paso_id": id, "instruccion_id": id, "codigo": ...}`), llama a `iluo.marcar_reevaluacion` y encola microlecciones y preguntas.
* `a_dict(bd, ins, con_pasos=True) -> dict` con URLs firmadas de imágenes y clips.
