import structlog

from app.config import settings
from app.guardrails.input import validate_input
from app.guardrails.output import enforce_scope_response
from app.prompts.loader import render_estimation_prompt
from app.schemas import EstimationRequest, EstimationResult, PromptVersion
from app.services.anchors import AnchorDetector
from app.services.boss import Boss, BossTrace
from app.services.compression import CompressionPolicy
from app.services.critic import Critic, CriticFeedback
from app.services.llm_service import EstimationOutput
from app.services.llm_wrapper import LLMWrapper
from app.services.project_memory import update_project_metadata
from app.services.summarizer import CumulativeSummarizer
from app.services.tier import Tier, resolve_tier
from app.services.usage_meter import MeteredLLM
from app.sessions import Session

log = structlog.get_logger()


def _history_user_text(transcript: str, attachment_names: list[str]) -> str:
    if not attachment_names:
        return transcript
    return f"{transcript}\n[Adjuntos: {', '.join(attachment_names)}]"


def _history_assistant_text(result: EstimationResult) -> str:
    phases = ", ".join(p.name for p in result.phases)
    return (
        f"{result.summary}\n"
        f"Total: {result.total_duration_weeks} semanas, {result.total_cost_eur} EUR. "
        f"Fases: {phases}."
    )


def _commit_turn(
    session: Session,
    request: EstimationRequest,
    transcript: str,
    attachment_names: list[str],
    result: EstimationResult,
    tier: Tier,
    tier_rule: str,
    llm_wrapper: LLMWrapper | MeteredLLM,
) -> None:
    """Único punto que muta la sesión, y solo con el resultado final del turno."""
    new_metadata = update_project_metadata(
        previous=session.project_metadata,
        transcript=request.description,
        result=result,
        llm_wrapper=llm_wrapper,
        model=settings.METADATA_EXTRACTOR_MODEL,
    )

    # solo tras el éxito se muta la sesión, todo junto
    session.history.add_turn(
        _history_user_text(transcript, attachment_names),
        _history_assistant_text(result),
    )
    session.project_metadata = new_metadata
    session.turn_count += 1
    session.last_resolved_tier = tier.value
    session.last_tier_rule = tier_rule

    policy = CompressionPolicy(
        AnchorDetector(),
        CumulativeSummarizer(llm_wrapper, settings.COMPRESSION_MODEL),
    )
    policy.apply(session.history)

    # solo ids y contadores: el contenido incluye datos del cliente
    log.info(
        "session_turn_completed",
        session_id=session.session_id,
        turns=session.history.turns,
        anchors=len(session.history.anchors) // 2,
        summary_chars=len(session.history.summary or ""),
        tier=tier.value,
        tier_rule=tier_rule,
        attachments=len(attachment_names),
        metadata_empty=session.project_metadata.is_empty(),
        technologies=len(session.project_metadata.mentioned_technologies),
    )


def generate_session_estimation(
    session: Session,
    request: EstimationRequest,   # description = transcript + texto de adjuntos
    transcript: str,              # solo lo que escribió el cliente
    attachment_names: list[str],
    version: PromptVersion = PromptVersion.V3,
    tier_override: Tier | None = None,
    *,
    llm_wrapper: LLMWrapper,
) -> EstimationOutput:
    # los adjuntos son input no confiable: se validan junto con el transcript
    validate_input(request.description)

    tier, tier_rule = resolve_tier(request.description, session.project_metadata, tier_override)

    # suma el consumo de las 2-3 llamadas del turno (estimación, metadata, resumen)
    meter = MeteredLLM(llm_wrapper)

    system_prompt, user_prompt = render_estimation_prompt(
        request, version, project_metadata=session.project_metadata, tier=tier
    )
    messages = session.history.to_messages_list(system_prompt, user_prompt)

    response = meter.complete_structured(
        messages=messages,
        max_tokens=settings.ESTIMATION_MAX_TOKENS,
        response_model=EstimationResult,
    )
    result = enforce_scope_response(response.parsed)

    _commit_turn(session, request, transcript, attachment_names, result, tier, tier_rule, meter)

    # evento agregado: una fila por turno para el CSV del stress test.
    # Se emite tras _commit_turn para leer el estado ya comprimido.
    u = meter.usage
    observed = dict(
        turn_index=session.turn_count,
        session_id=session.session_id,
        enriched_transcript_chars=len(request.description),
        # aproximado: incluye los marcadores "--- attachment ---" (~60 chars por adjunto)
        attachments_total_chars=max(0, len(request.description) - len(transcript)),
        messages_in_window=len(session.history.messages),
        anchors_count=len(session.history.anchors) // 2,
        summary_chars=len(session.history.summary or ""),
        tokens_in=u.tokens_in,
        tokens_out=u.tokens_out,
        cost_usd=round(u.cost_usd, 6),
        latency_ms=u.latency_ms,
        cache_hit_kind="none",  # el camino de sesiones no usa EstimationCache
        last_resolved_tier=tier.value,
        llm_calls=u.calls,
        unpriced_calls=u.unpriced_calls,
    )
    session.last_turn = observed
    log.info("turn_observed", **observed)

    return EstimationOutput(
        result=result,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        truncated=response.finish_reason == "length",
        model=response.model,
        provider=response.provider,
        system_prompt=system_prompt,
    )


def generate_session_estimation_acb(
    session: Session,
    request: EstimationRequest,
    transcript: str,
    attachment_names: list[str],
    version: PromptVersion = PromptVersion.V3,
    tier_override: Tier | None = None,
    *,
    llm_wrapper: LLMWrapper,
    max_iterations: int | None = None,
) -> tuple[EstimationOutput, BossTrace]:
    """Turno Actor-Critic-Boss. Los borradores intermedios se descartan: la sesión solo
    guarda el resultado final, así para el usuario un turno sigue siendo una respuesta.

    Peor caso con BOSS_MAX_ITERATIONS=3: 3 llamadas al actor + 3 al critic + 1 extractor
    + quizá 1 resumidor = 8, frente a 2-3 del flujo normal.
    """
    validate_input(request.description)

    tier, tier_rule = resolve_tier(request.description, session.project_metadata, tier_override)
    critic = Critic(llm_wrapper, settings.CRITIC_MODEL)

    # el actor acumula los tokens de todas sus llamadas y recuerda la última respuesta
    usage = {"input": 0, "output": 0, "truncated": False}
    last: dict = {}

    def actor(feedback: CriticFeedback | None) -> EstimationResult:
        system_prompt, user_prompt = render_estimation_prompt(
            request, version, project_metadata=session.project_metadata,
            tier=tier, critic_feedback=feedback,
        )
        messages = session.history.to_messages_list(system_prompt, user_prompt)
        response = llm_wrapper.complete_structured(
            messages=messages,
            max_tokens=settings.ESTIMATION_MAX_TOKENS,
            response_model=EstimationResult,
        )
        usage["input"] += response.input_tokens
        usage["output"] += response.output_tokens
        usage["truncated"] |= response.finish_reason == "length"
        last.update(response=response, system_prompt=system_prompt)
        return enforce_scope_response(response.parsed)

    def critic_fn(draft: EstimationResult) -> CriticFeedback:
        return critic.review(request.description, session.project_metadata, tier, draft)

    boss = Boss(max_iterations or settings.BOSS_MAX_ITERATIONS)
    result, trace = boss.run(actor, critic_fn)

    _commit_turn(session, request, transcript, attachment_names, result, tier, tier_rule, llm_wrapper)

    log.info(
        "acb_turn_completed",
        session_id=session.session_id,
        iterations=len(trace.iterations),
        outcome=trace.outcome.value if trace.outcome else None,
    )

    output = EstimationOutput(
        result=result,
        input_tokens=usage["input"],
        output_tokens=usage["output"],
        truncated=usage["truncated"],
        model=last["response"].model,
        provider=last["response"].provider,
        system_prompt=last["system_prompt"],
    )
    return output, trace
