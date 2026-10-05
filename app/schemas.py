from enum import Enum

from pydantic import BaseModel, Field, model_validator


class ProjectType(str, Enum):
    MOBILE_APP = "mobile_app"
    WEB_SAAS = "web_saas"
    INTERNAL_TOOL = "internal_tool"
    DATA_PIPELINE = "data_pipeline"


class DetailLevel(str, Enum):
    SUMMARY = "summary"
    MEDIUM = "medium"
    DETAILED = "detailed"


class OutputFormat(str, Enum):
    PHASES_TABLE = "phases_table"
    LINE_ITEMS = "line_items"
    NARRATIVE = "narrative"


class PromptVersion(str, Enum):
    """Versiones disponibles en app/prompts/estimation/<version>/."""

    V1 = "v1"
    V2 = "v2"


class EstimationRequest(BaseModel):
    description: str = Field(min_length=20, max_length=2000)
    project_type: ProjectType
    detail_level: DetailLevel
    output_format: OutputFormat

class Phase(BaseModel):
    name: str
    duration_weeks: int = Field(ge=1, le=52)
    cost_eur: int = Field(gt=0)
    confidence_pct: int = Field(ge=0, le=100)
    assumptions: list[str]

class EstimationResult(BaseModel):
    summary: str
    total_duration_weeks: int = Field(ge=1)
    total_cost_eur: int = Field(gt=0)
    confidence_pct: int = Field(ge=0, le=100)
    phases: list[Phase] = Field(min_length=1)

    @model_validator(mode="after")
    def totals_must_match_phases(self):
        sum_weeks = sum(phase.duration_weeks for phase in self.phases)
        sum_costs = sum(phase.cost_eur for phase in self.phases)
        if abs(sum_weeks - self.total_duration_weeks) > 1:
            raise ValueError(
                f"total_duration_weeks is {self.total_duration_weeks} but phases sum to {sum_weeks}"
            )
        if abs(sum_costs - self.total_cost_eur) > max(1, self.total_cost_eur * 0.02):
            raise ValueError(
                f"total_cost_eur is {self.total_cost_eur} but phases sum to {sum_costs}"
            )
        return self

class EstimationResponse(BaseModel):
    result: EstimationResult
    prompt_version: str
    system_prompt: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    truncated: bool
    cache_hit: bool
