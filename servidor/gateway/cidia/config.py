"""Ajustes del servicio, leídos de variables de entorno con prefijo CIDIA_."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Ajustes(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CIDIA_", env_file=".env", extra="ignore")

    entorno: str = "desarrollo"  # desarrollo | produccion
    nombre_servidor: str = "Servidor CidIA"

    # Base de datos
    base_datos_url: str = "postgresql+pg8000://cidia:cidia@localhost:5432/cidia"

    # Sesiones
    secreto_jwt: str = "cambia-este-secreto-en-produccion"
    duracion_sesion_horas: int = 12
    duracion_invitado_horas: int = 4
    invitado_limite_hora: int = 30  # peticiones por hora y sesión de invitado

    # Ficheros
    dir_datos: Path = Path("./datos")
    dir_web: Path = Path("../web/dist")  # interfaz compilada que se sirve en /app
    url_publica: str = "http://localhost:8080"

    # Modelos (endpoint compatible con OpenAI, normalmente Ollama)
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_modelo_chat: str = "qwen3:0.6b"  # si la tabla de modelos está vacía
    llm_modelo_embeddings: str = "qwen3-embedding:0.6b"
    llm_modelo_vision: str = ""  # vacío: no hay modelo con visión
    llm_timeout: float = 300.0
    llm_contexto: int = 8192
    llm_sin_razonamiento: bool = True  # pide reasoning_effort="none" (los modelos que razonan contestan antes)
    llm_instruccion_consulta: str = (
        "Instruct: Dada una pregunta de un trabajador de una planta industrial, "
        "recupera los fragmentos que la responden\nQuery: "
    )

    # Voz
    asr_base_url: str = "http://localhost:8000/v1"
    asr_modelo: str = "base"
    asr_idioma: str = "es"

    # Conocimiento
    motor_conocimiento: str = "pgvector"  # pgvector | weknora
    weknora_url: str = "http://weknora:8080/api/v1"
    weknora_api_key: str = ""
    umbral_respaldo: float = 0.40  # similitud mínima (qwen3-embedding: lo ajeno ronda 0,35 y lo relevante 0,6-0,8)
    fragmentos_por_consulta: int = 6

    # Espacio de trabajo del agente
    espacio_url: str = "http://espacio-trabajo:8090"
    espacio_secreto: str = ""

    # Política de modelos
    permitir_modelos_nube: bool = False

    # Arranque
    crear_semilla: bool = False
    admin_usuario: str = "admin"
    admin_contrasena: str = ""  # si se define y no hay administrador, se crea
    demo_contrasena: str = ""  # contraseña de los usuarios sintéticos de la semilla
    cors_origenes: list[str] = ["*"]

    @property
    def es_produccion(self) -> bool:
        return self.entorno == "produccion"


@lru_cache
def ajustes() -> Ajustes:
    a = Ajustes()
    a.dir_datos.mkdir(parents=True, exist_ok=True)
    return a
