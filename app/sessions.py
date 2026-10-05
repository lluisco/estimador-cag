"""Estado conversacional del estimator: historial (ventana deslizante) + project_metadata.

Dos conceptos distintos que NO se mezclan:

- Historial: el array ``messages`` que viaja a la API del LLM en cada llamada.
  Es volátil y acotado: solo los últimos N turnos.
- Memoria (project_metadata): los hechos del proyecto en curso (nombre, equipo,
  tecnologías, alcance). Sobrevive a la ventana: aunque un turno antiguo salga del
  historial, sus hechos siguen en el system prompt.

Persistencia: todo vive en un diccionario en memoria del proceso. Se pierde al
reiniciar el servicio y no se comparte entre workers. Lo aceptamos en esta fase
porque simplifica el ejercicio (sin BBDD ni Redis) y el objetivo es el patrón,
no la durabilidad.
"""

from uuid import uuid4

from pydantic import BaseModel, Field

MAX_TURNS = 6


class ProjectMetadata(BaseModel):
    """Hechos conocidos del proyecto en curso. Vacío en la primera llamada de la sesión."""

    project_name: str | None = None
    assumed_team_size: int | None = None
    mentioned_technologies: list[str] = Field(default_factory=list)
    agreed_scope: str = ""

    def is_empty(self) -> bool:
        return not self.model_dump(exclude_defaults=True)


class ConversationHistory:
    """Mensajes user/assistant con ventana deslizante de ``max_turns`` turnos.

    Un turno es un par user+assistant. El system prompt NO se almacena aquí:
    se regenera en cada llamada a partir del project_metadata actual, así
    es invariante por construcción y nunca puede ser descartado por la ventana.
    """

    def __init__(self, max_turns: int = MAX_TURNS):
        self.max_turns = max_turns
        self._messages: list[dict] = []

    def add_turn(self, user_message: str, assistant_message: str) -> None:
        self._messages.append({"role": "user", "content": user_message})
        self._messages.append({"role": "assistant", "content": assistant_message})
        # cada turno son 2 mensajes: descartamos los pares más antiguos
        excess = len(self._messages) - self.max_turns * 2
        if excess > 0:
            del self._messages[:excess]

    @property
    def turns(self) -> int:
        return len(self._messages) // 2

    def to_messages_list(self, system_prompt: str, new_user_message: str | None = None) -> list[dict]:
        stored = self._messages
        if new_user_message is not None:
            # el mensaje nuevo cuenta como un turno, dejamos hueco para el.
            keep = (self.max_turns - 1) * 2
            stored = stored[-keep:] if keep > 0 else []
        messages = [{"role": "system", "content": system_prompt}, *stored]
        if new_user_message is not None:
            messages.append({"role": "user", "content": new_user_message})
        return messages
        


class Session:
    def __init__(self, session_id: str, max_turns: int = MAX_TURNS):
        self.session_id = session_id
        self.history = ConversationHistory(max_turns)
        self.project_metadata = ProjectMetadata()


# session_id -> Session. Ver nota de volatilidad en el docstring del módulo.
_sessions: dict[str, Session] = {}


def create_session(max_turns: int = MAX_TURNS) -> Session:
    session = Session(session_id=str(uuid4()), max_turns=max_turns)
    _sessions[session.session_id] = session
    return session


def get_session(session_id: str) -> Session | None:
    return _sessions.get(session_id)
