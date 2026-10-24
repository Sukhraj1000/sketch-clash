"""Validated wire contracts; model output never enters the simulation unchecked."""
from __future__ import annotations
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

Identifier = Annotated[str, Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_:-]+$')]
Slot = Literal[0, 1]

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Crop(Contract):
    x: int = Field(ge=0, strict=True)
    y: int = Field(ge=0, strict=True)
    width: int = Field(gt=0, strict=True)
    height: int = Field(gt=0, strict=True)

class Detection(Contract):
    id: str = Field(max_length=100)
    label: str = Field(max_length=100)
    score: float = Field(ge=0, le=1)
    box: Crop

class CombatStats(Contract):
    health: Literal[100] = 100
    attack: int = Field(ge=12, le=24, strict=True)
    defense: int = Field(ge=0, le=8, strict=True)
    speed: int = Field(ge=1, le=3, strict=True)

class Proportions(Contract):
    width: float = Field(default=1, ge=.7, le=1.4)
    height: float = Field(default=1, ge=.7, le=1.4)

class VisualSpec(Contract):
    template_id: Literal['mug', 'bottle', 'generic', 'plant', 'book', 'ball']
    palette: list[str] = Field(min_length=1, max_length=4)
    scale: float = Field(default=1, ge=.7, le=1.4)
    proportions: Proportions = Field(default_factory=Proportions)
    accessories: list[Literal['eyes', 'arms', 'feet', 'leaf', 'handle', 'cap']] = Field(default_factory=list, max_length=4)
    animation_style: Literal['bouncy', 'calm', 'wobbly'] = 'bouncy'
    schema_version: Literal['1'] = '1'
    appearance_seed: int = Field(ge=0, le=2147483647, strict=True)

    @field_validator('palette')
    @classmethod
    def colours(cls, value: list[str]) -> list[str]:
        import re
        if not all(re.fullmatch(r'#[0-9A-Fa-f]{6}', x) for x in value):
            raise ValueError('Colours must be six-digit hexadecimal values.')
        return value

class ObservedObject(Contract):
    canonical_type_id: str | None = Field(default=None, max_length=100)
    label: str | None = Field(default=None, max_length=100)
    visible_features: list[str] = Field(default_factory=list, max_length=24)

class RoundTheme(Contract):
    id: str
    name: str
    instructions: str
    examples: list[str]
    rotation_index: int | None = None
    policy_version: str
    enforced: bool = True

class ThemeValidation(Contract):
    theme_id: str
    theme_name: str
    policy_version: str
    verdict: Literal['eligible', 'outside_theme', 'uncertain']
    reason: str
    evidence_labels: list[str] = Field(default_factory=list)
    basis: Literal['recognition_identity_rules'] = 'recognition_identity_rules'
    resolution: Literal['confirm_identity'] | None = None

class FeedbackSubmission(Contract):
    idempotency_key: Identifier
    output_id: Identifier
    pipeline_version_id: Identifier
    recognition_verdict: Literal['correct', 'corrected', 'unsure']
    creative_verdict: Literal['keep', 'change', 'skipped'] = 'skipped'
    correction_label: str | None = Field(default=None, min_length=1, max_length=80)
    selected_target: Crop | None = None
    reasons: list[Literal['resemblance', 'colour_proportions', 'name', 'style_accessory', 'rendering_defect']] = Field(default_factory=list, max_length=5)
    comment: str = Field(default='', max_length=600)
    shared_consent: bool = False

class CorrectionRequest(Contract):
    idempotency_key: Identifier
    output_id: Identifier
    pipeline_version_id: Identifier
    kind: Literal['factual', 'style']
    canonical_label: str | None = Field(default=None, min_length=1, max_length=80)
    details: str = Field(default='', max_length=600)
    reasons: list[Literal['resemblance', 'colour_proportions', 'name', 'style_accessory', 'rendering_defect']] = Field(default_factory=list, max_length=5)

class PendingFighter(Contract):
    combat_profile: dict[str, Any] | None = None
    market_price: dict[str, Any] | None = None
    output_id: str | None = None
    pipeline_version_id: str = 'legacy-unknown'
    parent_output_id: str | None = None
    observed_object: ObservedObject | None = None
    battle_id: Identifier
    player_slot: Slot
    capture_id: Identifier
    image_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    canonical_type_id: str = Field(min_length=1, max_length=100, pattern=r'^[a-z0-9_-]+$')
    object_type: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=64)
    image_ref: str = Field(pattern=r'^/api/media/[a-f0-9]{64}$')
    archetype: Literal['Quick', 'Power', 'Guard']
    stats: CombatStats
    visual_spec: VisualSpec
    validation: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    config_versions: dict[str, str] = Field(default_factory=dict)

class Observation(Contract):
    theme_validation: ThemeValidation | None = None
    output_id: str | None = None
    pipeline_version_id: str = 'legacy-unknown'
    parent_output_id: str | None = None
    observed_object: ObservedObject | None = None
    saved_resident_preview: dict[str, Any] | None = None
    capture_id: Identifier
    source: Literal['camera', 'upload']
    image_ref: str
    image_hash: str
    width: int = Field(gt=0, le=16000)
    height: int = Field(gt=0, le=16000)
    crop: Crop | None = None
    status: Literal['recognized', 'needs_selection', 'needs_recapture']
    proposed_label: str | None = Field(default=None, max_length=100)
    canonical_type_candidate: str | None = Field(default=None, max_length=100)
    visible_features: list[str] = Field(default_factory=list, max_length=24)
    uncertainty: list[str] = Field(default_factory=list, max_length=16)
    candidates: list[Detection] = Field(default_factory=list, max_length=12)
    evidence: dict[str, Any] = Field(default_factory=dict)
    pending_fighter: PendingFighter | None = None
    stale: bool = False

class CreateBattle(Contract):
    request_id: Identifier

class ConfirmCapture(Contract):
    player_slot: Slot
    capture_id: Identifier

class StartBattle(Contract):
    playback_mode: Literal['normal', 'reduced', 'quick'] = 'normal'

class SelectCapture(Contract):
    crop: Crop

class BattleEvent(Contract):
    id: str
    at: int = Field(ge=0)
    attacker: Slot
    damage: int = Field(ge=1, le=100)
    kind: Literal['swipe', 'heavy', 'finisher']
    word: str
    receipt: dict[str, Any] | None = None

class Battle(Contract):
    theme: RoundTheme | None = None
    pipeline_version_id: str = 'legacy-unknown'
    id: Identifier
    request_id: Identifier
    world_id: Identifier
    status: Literal['draft', 'ready', 'running', 'completed', 'cancelled', 'failed']
    created_at: str
    updated_at: str
    active_capture_ids: list[str | None]
    confirmed_capture_ids: list[str | None] = Field(default_factory=lambda: [None, None])
    pending_fighters: list[PendingFighter | None]
    fighters: list[PendingFighter] = Field(default_factory=list)
    events: list[BattleEvent] = Field(default_factory=list)
    seed: int | None = None
    engine_version: str | None = None
    winner_slot: Slot | None = None
    final_health: list[int] | None = None
    playback_mode: Literal['normal', 'reduced', 'quick'] | None = None
    duration_ms: int | None = None
    started_at: str | None = None
    eligible_at: str | None = None
    completed_at: str | None = None
    completion: dict[str, Any] | None = None
    combat: dict[str, Any] | None = None
    persistence: Literal['mongodb', 'development_memory']
