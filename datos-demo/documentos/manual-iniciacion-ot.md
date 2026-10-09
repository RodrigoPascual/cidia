# Manual de iniciación a Oficina técnica

> Documento sintético de demostración. Metalúrgica Arlanza, S. L. es una empresa ficticia; personas, proveedores, precios y referencias son inventados.

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
