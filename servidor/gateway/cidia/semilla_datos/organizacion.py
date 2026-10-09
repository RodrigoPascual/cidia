"""Organización sintética de Metalúrgica Arlanza, S. L. (empresa ficticia de Burgos)."""

from __future__ import annotations

EMPRESA = {
    "nombre": "Metalúrgica Arlanza, S. L.",
    "sector": "Estampación, soldadura y montaje de conjuntos metálicos (empresa ficticia de demostración)",
}

DOMINIO_CORREO = "arlanza.example"  # dominio reservado para ejemplos: nunca recibe correo real

DEPARTAMENTOS = [
    {
        "clave": "prod", "nombre": "Producción", "codigo": "PROD", "color": "#d97a00",
        "descripcion": "Prensas, línea 2 de montaje de colectores y soldadura. Tres turnos en prensas y dos en montaje.",
    },
    {
        "clave": "ot", "nombre": "Oficina técnica", "codigo": "OT", "color": "#2f6fbf",
        "descripcion": "Diseño de utillajes, revisión de planos de cliente, hojas de proceso y costes de utillaje.",
    },
    {
        "clave": "cal", "nombre": "Calidad", "codigo": "CAL", "color": "#1f8a70",
        "descripcion": "Laboratorio metrológico, control de primera pieza, inspección en línea y producto no conforme.",
    },
    {
        "clave": "mant", "nombre": "Mantenimiento", "codigo": "MANT", "color": "#c8442f",
        "descripcion": "Mantenimiento preventivo y correctivo de prensas, línea 2 e instalaciones; consignaciones.",
    },
]

# Riesgos frecuentes (se combinan en las tareas)
_PVD = "Trabajo con pantallas de visualización: pausas de 10 minutos cada 2 horas. En visitas a planta, EPIs de la zona."
_PRENSA = "Atrapamiento en la zona de trabajo de la prensa; cortes con recortes de chapa; ruido de impacto (88 dB(A))."

PUESTOS = [
    # ------------------------------------------------------------------ Producción
    {
        "clave": "montaje_l2", "departamento": "prod", "nombre": "Montaje línea 2",
        "descripcion": "Montaje de los colectores CL-200: bridas, soportes laterales, prueba de estanqueidad y embalaje.",
        "tareas": [
            {"codigo": "IT-023", "nombre": "Montaje de la brida B", "criticidad": 3, "nivel_minimo": 1,
             "descripcion": "Montaje de la brida B (BR-B-080) sobre el colector CL-200 en la estación E2 de la línea 2.",
             "riesgos_prl": "Atrapamiento de dedos al presentar la brida; sobreesfuerzo en el apriete; proyección de "
                            "aire en la prueba de estanqueidad."},
            {"codigo": "IT-024", "nombre": "Montaje de soportes laterales", "criticidad": 2, "nivel_minimo": 1,
             "descripcion": "Atornillado de los soportes SL-12 en la estación E3 con atornillador de embrague.",
             "riesgos_prl": "Golpes y cortes con aristas; ruido del atornillador (80 dB(A)); posturas forzadas."},
            {"codigo": "IT-025", "nombre": "Cambio de bobina de film en la enfardadora", "criticidad": 1,
             "nivel_minimo": 1,
             "descripcion": "Sustitución de la bobina de film estirable en la estación E6 de embalaje.",
             "riesgos_prl": "Cortes con el film y el cúter; atrapamiento en el carro de la enfardadora."},
        ],
    },
    {
        "clave": "prensas", "departamento": "prod", "nombre": "Prensas",
        "descripcion": "Manejo, cambio de molde y despeje de atascos en las prensas P1 a P4 de la nave 1.",
        "tareas": [
            {"codigo": "IT-031", "nombre": "Cambio de molde en la prensa 3", "criticidad": 3, "nivel_minimo": 1,
             "descripcion": "Cambio rápido de molde en la prensa P3 (630 t) con carro de cambio y amarres hidráulicos.",
             "riesgos_prl": "Atrapamiento grave entre molde y mesa; caída de cargas (moldes de hasta 1.800 kg); "
                            "energía hidráulica residual; quemaduras con el molde caliente."},
            {"codigo": "IT-032", "nombre": "Arranque y parada segura de prensa", "criticidad": 3, "nivel_minimo": 1,
             "descripcion": "Comprobaciones de arranque, prueba de resguardos y parada al final del turno.",
             "riesgos_prl": _PRENSA},
            {"codigo": "IT-033", "nombre": "Despeje de atascos en la prensa", "criticidad": 3, "nivel_minimo": 1,
             "descripcion": "Retirada segura de piezas o recortes atascados en el molde.",
             "riesgos_prl": _PRENSA + " Rearme accidental si no se consigna."},
        ],
    },
    {
        "clave": "soldadura", "departamento": "prod", "nombre": "Soldadura",
        "descripcion": "Soldadura MAG manual de soportes y preparación de la célula robotizada R2.",
        "tareas": [
            {"codigo": "IT-041", "nombre": "Soldadura MAG de soportes", "criticidad": 2, "nivel_minimo": 1,
             "descripcion": "Soldadura MAG de los soportes SL-12 en el utillaje UT-2025-014.",
             "riesgos_prl": "Radiación ultravioleta; humos de soldadura; quemaduras; incendio por proyecciones."},
            {"codigo": "IT-042", "nombre": "Preparación de la célula de soldadura robotizada", "criticidad": 2,
             "nivel_minimo": 2,
             "descripcion": "Carga del programa, cambio de utillaje y comprobación de la antorcha en la célula R2.",
             "riesgos_prl": "Atrapamiento con el robot; arco eléctrico; humos de soldadura."},
        ],
    },
    # ------------------------------------------------------------------ Oficina técnica
    {
        "clave": "utillajes", "departamento": "ot", "nombre": "Diseño de utillajes",
        "descripcion": "Diseño de utillajes de soldadura y control, revisión de planos de cliente y costes.",
        "tareas": [
            {"codigo": "IT-051", "nombre": "Diseño de utillaje de soldadura", "criticidad": 2, "nivel_minimo": 1,
             "descripcion": "Diseño de un utillaje manual de soldadura con referencias 3-2-1, amarres y planos.",
             "riesgos_prl": _PVD},
            {"codigo": "IT-052", "nombre": "Revisión de planos de cliente", "criticidad": 2, "nivel_minimo": 1,
             "descripcion": "Revisión de la viabilidad de fabricación de un plano de cliente antes de ofertar.",
             "riesgos_prl": _PVD},
            {"codigo": "IT-053", "nombre": "Cálculo de costes de utillaje", "criticidad": 1, "nivel_minimo": 3,
             "descripcion": "Estimación del coste de un utillaje y comparación de ofertas de proveedores.",
             "riesgos_prl": _PVD},
        ],
    },
    {
        "clave": "procesos", "departamento": "ot", "nombre": "Ingeniería de procesos",
        "descripcion": "Hojas de proceso, tiempos estándar y altas de referencias en el ERP.",
        "tareas": [
            {"codigo": "IT-055", "nombre": "Elaboración de hojas de proceso", "criticidad": 2, "nivel_minimo": 2,
             "descripcion": "Definición de operaciones, máquinas, utillajes y tiempos de una referencia nueva.",
             "riesgos_prl": _PVD},
            {"codigo": "IT-056", "nombre": "Alta de una nueva referencia en el ERP", "criticidad": 1,
             "nivel_minimo": 1,
             "descripcion": "Alta de artículo, lista de materiales y ruta en el ERP.",
             "riesgos_prl": _PVD},
        ],
    },
    # ------------------------------------------------------------------ Calidad
    {
        "clave": "laboratorio", "departamento": "cal", "nombre": "Laboratorio metrológico",
        "descripcion": "Mediciones dimensionales, calibración interna y verificación de llaves dinamométricas.",
        "tareas": [
            {"codigo": "IT-061", "nombre": "Inspección dimensional con calibre", "criticidad": 2, "nivel_minimo": 1,
             "descripcion": "Medición de las cotas del plan de control con calibre digital de 150 mm.",
             "riesgos_prl": "Cortes con aristas de piezas sin desbarbar; posturas forzadas en la mesa de medición."},
            {"codigo": "IT-062", "nombre": "Medición con micrómetro de exteriores", "criticidad": 2,
             "nivel_minimo": 1,
             "descripcion": "Medición de diámetros con micrómetro de 0-25 mm y 25-50 mm.",
             "riesgos_prl": "Cortes con aristas de piezas sin desbarbar."},
            {"codigo": "IT-063", "nombre": "Verificación de llaves dinamométricas", "criticidad": 3,
             "nivel_minimo": 2,
             "descripcion": "Verificación semestral de las llaves dinamométricas de la planta en el banco de par.",
             "riesgos_prl": "Golpes por liberación brusca del par; atrapamiento de dedos en el banco."},
        ],
    },
    {
        "clave": "inspeccion", "departamento": "cal", "nombre": "Inspección en línea",
        "descripcion": "Control de primera pieza, auditorías de producto y gestión de no conformidades en planta.",
        "tareas": [
            {"codigo": "IT-065", "nombre": "Control de primera pieza", "criticidad": 3, "nivel_minimo": 1,
             "descripcion": "Liberación de la primera pieza tras un cambio de molde, de turno o de lote de material.",
             "riesgos_prl": "Circulación de carretillas; proximidad de prensas en marcha."},
            {"codigo": "IT-066", "nombre": "Gestión de producto no conforme", "criticidad": 2, "nivel_minimo": 1,
             "descripcion": "Identificación, segregación y registro de piezas no conformes.",
             "riesgos_prl": "Sobreesfuerzos al mover contenedores; circulación de carretillas."},
        ],
    },
    # ------------------------------------------------------------------ Mantenimiento
    {
        "clave": "mecanico", "departamento": "mant", "nombre": "Mantenimiento mecánico",
        "descripcion": "Preventivo y correctivo mecánico e hidráulico de prensas y línea 2.",
        "tareas": [
            {"codigo": "IT-071", "nombre": "Calibración del sensor S4 de la prensa 3", "criticidad": 2,
             "nivel_minimo": 2,
             "descripcion": "Ajuste de la distancia de detección del sensor inductivo S4 (presencia de pieza).",
             "riesgos_prl": "Atrapamiento si la prensa no está consignada; caída a distinto nivel desde la "
                            "plataforma de acceso."},
            {"codigo": "IT-072", "nombre": "Engrase de guías de prensa", "criticidad": 1, "nivel_minimo": 1,
             "descripcion": "Engrase de las guías del carro de las prensas según el plan preventivo.",
             "riesgos_prl": "Atrapamiento si la prensa no está consignada; resbalones por aceite."},
            {"codigo": "IT-073", "nombre": "Consignación de la prensa 3", "criticidad": 3, "nivel_minimo": 1,
             "descripcion": "Bloqueo y señalización de todas las energías de la prensa P3 antes de intervenir.",
             "riesgos_prl": "Energías residuales: eléctrica, hidráulica, neumática y gravedad (carro en alto)."},
        ],
    },
    {
        "clave": "electrico", "departamento": "mant", "nombre": "Mantenimiento eléctrico",
        "descripcion": "Cuadros, automatismos, sensores y dispositivos de seguridad.",
        "tareas": [
            {"codigo": "IT-075", "nombre": "Sustitución de la barrera fotoeléctrica de seguridad", "criticidad": 3,
             "nivel_minimo": 2,
             "descripcion": "Cambio y prueba de la barrera fotoeléctrica de una prensa (función de seguridad).",
             "riesgos_prl": "Riesgo eléctrico; pérdida de la función de seguridad si la prueba no es completa."},
            {"codigo": "IT-076", "nombre": "Revisión termográfica de cuadros eléctricos", "criticidad": 2,
             "nivel_minimo": 2,
             "descripcion": "Inspección con cámara termográfica de los cuadros de prensas y línea 2.",
             "riesgos_prl": "Contacto eléctrico indirecto; arco eléctrico al abrir cuadros en tensión."},
        ],
    },
]

# usuario, nombre, departamento, nivel (orden), rol, experto, puesto
PERSONAS = [
    ("javier", "Javier Martín", "prod", 3, "jefe", True, "prensas"),
    ("carmen", "Carmen Díaz", "prod", 2, "empleado", True, "montaje_l2"),
    ("marta", "Marta Sanz", "prod", 2, "empleado", False, "montaje_l2"),
    ("pedro", "Pedro Ruiz", "prod", 1, "empleado", False, "prensas"),
    ("lucia", "Lucía Herrero", "prod", 1, "empleado", False, "montaje_l2"),
    ("ana", "Ana López", "ot", 3, "jefe", True, "utillajes"),
    ("luis", "Luis García", "ot", 1, "empleado", False, "utillajes"),
    ("raul", "Raúl Gómez", "ot", 2, "empleado", False, "procesos"),
    ("elena", "Elena Moreno", "cal", 3, "jefe", True, "laboratorio"),
    ("david", "David Ortega", "cal", 2, "empleado", False, "laboratorio"),
    ("irene", "Irene Castro", "cal", 1, "empleado", False, "inspeccion"),
    ("jorge", "Jorge Barrio", "mant", 3, "jefe", True, "electrico"),
    ("nuria", "Nuria Gil", "mant", 2, "empleado", True, "mecanico"),
    ("oscar", "Óscar Peña", "mant", 2, "empleado", False, "mecanico"),
]

ADMIN = ("admin", "Administración", None, 4, "admin", False, None)

# Formaciones cruzadas: dan acceso al material de formación del otro departamento.
FORMACIONES = [
    {"usuario": "marta", "departamento": "ot", "puesto": "utillajes", "estado": "activa",
     "inicio": 21, "fin_previsto": -35, "asignada_por": "ana"},
    {"usuario": "irene", "departamento": "prod", "puesto": "prensas", "estado": "activa",
     "inicio": 9, "fin_previsto": -50, "asignada_por": "javier"},
    {"usuario": "david", "departamento": "ot", "puesto": "procesos", "estado": "completada",
     "inicio": 150, "fin_previsto": 90, "asignada_por": "ana"},
]
