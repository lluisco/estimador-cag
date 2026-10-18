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
no la durabilidad. ``SessionStore`` es la única pieza a sustituir el día que haga
falta persistencia.
"""

from uuid import uuid4

from pydantic import BaseModel, Field

from app.config import settings

MAX_TURNS = settings.SESSION_MAX_TURNS


class ProjectMetadata(BaseModel):
    """Hechos conocidos del proyecto en curso. Vacío en la primera llamada de la sesión."""

    project_name: str | None = Field(default=None, max_length=120)
    assumed_team_size: int | None = Field(default=None, ge=1, le=50)
    mentioned_technologies: list[str] = Field(default_factory=list)
    agreed_scope: str | None = Field(default=None, max_length=2000)

    def is_empty(self) -> bool:
        return not self.model_dump(exclude_defaults=True)

    def merge_with(self, update: "ProjectMetadata") -> "ProjectMetadata":
        """Fusiona en código, no en el LLM: los escalares se sobrescriben solo si
        ``update`` trae valor, y las tecnologías se unen sin distinguir mayúsculas,
        así el extractor no puede borrar un hecho ya conocido."""
        technologies = list(self.mentioned_technologies)
        seen = {tech.lower() for tech in technologies}
        for tech in update.mentioned_technologies:
            if tech.lower() not in seen:
                technologies.append(tech)
                seen.add(tech.lower())

        return ProjectMetadata(
            project_name=update.project_name or self.project_name,
            assumed_team_size=update.assumed_team_size or self.assumed_team_size,
            mentioned_technologies=technologies,
            agreed_scope=update.agreed_scope or self.agreed_scope,
        )


class ConversationHistory:
    """Mensajes user/assistant con ventana deslizante de ``max_turns`` turnos.

    Un turno es un par user+assistant. Se guardan como máximo ``max_turns`` pares;
    el mensaje en curso viaja aparte, así que al LLM le llegan hasta ``max_turns``
    pares previos + el mensaje nuevo.

    El system prompt NO se almacena aquí: se regenera en cada llamada a partir del
    project_metadata actual, así es invariante por construcción y nunca puede ser
    descartado por la ventana.
    """

    def __init__(self, max_turns: int = MAX_TURNS):
        self.max_turns = max_turns
        self.summary: str | None = None
        self.anchors: list[dict] = []
        self._messages: list[dict] = []

    def add_turn(self, user_message: str, assistant_message: str) -> None:
        self._messages.append({"role": "user", "content": user_message})
        self._messages.append({"role": "assistant", "content": assistant_message})

    def pop_oldest_turn(self) -> tuple[dict, dict]:
        user, assistant = self._messages[0], self._messages[1]
        del self._messages[:2]
        return user, assistant

    @property
    def turns(self) -> int:
        return len(self._messages) // 2

    @property
    def messages(self) -> list[dict]:
        return list(self._messages)

    def to_messages_list(self, system_prompt: str, new_user_message: str | None = None) -> list[dict]:
        if self.summary:
            system_prompt = (
                f"{system_prompt}\n\n"
                f"<conversation_summary>\n{self.summary}\n</conversation_summary>"
            )
        messages = [
            {"role": "system", "content": system_prompt},
            *self.anchors,
            *self._messages
        ]
        if new_user_message is not None:
            messages.append({"role": "user", "content": new_user_message})
        return messages


class Session:
    def __init__(self, session_id: str, max_turns: int = MAX_TURNS):
        self.session_id = session_id
        self.history = ConversationHistory(max_turns)
        self.project_metadata = ProjectMetadata()
        self.last_resolved_tier: str | None = None
        self.last_tier_rule: str | None = None


class SessionStore:
    """``session_id -> Session`` en memoria del proceso. Ver nota de volatilidad arriba.

    Sin locks: con un único worker de uvicorn basta. Con varios workers cada uno
    tendría su propia copia y la conversación se rompería entre peticiones.
    """

    def __init__(self, *, max_turns: int = MAX_TURNS):
        self._sessions: dict[str, Session] = {}
        self._max_turns = max_turns

    def create(self) -> Session:
        session = Session(session_id=str(uuid4()), max_turns=self._max_turns)
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def __len__(self) -> int:
        return len(self._sessions)


_store = SessionStore()


def get_session_store() -> SessionStore:
    """Dependencia de FastAPI; los tests la sustituyen con ``dependency_overrides``."""
    return _store
