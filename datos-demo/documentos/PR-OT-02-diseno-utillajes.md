# Procedimiento de diseño de utillajes (PR-OT-02, revisión B)

> Documento sintético de demostración. Metalúrgica Arlanza, S. L. es una empresa ficticia; personas, proveedores, precios y referencias son inventados.

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
