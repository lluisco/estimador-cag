import structlog
log = structlog.get_logger()

from app.services.llm_service import _wrapper
from app.sessions import ProjectMetadata

EXTRACTOR_SYSTEM = """You maintain the memory of a software project estimation conversation.
Given the known project facts, the client's latest message and the estimate just produced,
return the UPDATED project facts.
- Only record facts stated by the client or present in their documents. Never invent.
- Keep known facts unless the client's message corrects them.
- If a field is unknown, leave it empty / null.
- agreed_scope: 1-3 sentences, in Spanish."""

def merge_metadata(current: ProjectMetadata, new: ProjectMetadata) -> ProjectMetadata:
    return ProjectMetadata(
        project_name=new.project_name or current.project_name,
        assumed_team_size=new.assumed_team_size or current.assumed_team_size,
        # unión sin duplicados, conservando el orden
        mentioned_technologies=list(dict.fromkeys(
            [*current.mentioned_technologies, *new.mentioned_technologies]
        )),
        agreed_scope=new.agreed_scope or current.agreed_scope,
    )

def update_project_metadata(
    current: ProjectMetadata, transcript: str, estimation_summary: str        
) -> ProjectMetadata:
    user_message = (
        f"<known_facts>\n{current.model_dump_json(indent=2)}\n</known_facts>\n\n"
        f"<client_message>\n{transcript}\n</client_message>\n\n"
        f"<estimate_summary>\n{estimation_summary}\n</estimate_summary>"
    )
    try:
        response = _wrapper.complete_structured(
            system_prompt=EXTRACTOR_SYSTEM,
            user_message=user_message,
            response_model=ProjectMetadata,
            max_tokens=500,
        )
    except Exception as exc:
        log.warning("metadata_extraction_failed", error_type=type(exc).__name__)
        return current
    return merge_metadata(current, response.parsed)