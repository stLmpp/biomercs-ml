from dataclasses import dataclass
from typing import Literal

LabelKind = Literal["bullet_kill", "bonus_kill", "mixed"]


@dataclass
class HudSample:
    timestamp_s: float
    session_id: int
    timer_value_s: float | None
    combo_value: int | None
    confidence: float
    pickup_popup: bool = False
    bonus_popup: bool = False


@dataclass
class RawHudSample:
    timestamp_s: float
    timer_value_s: float | None
    combo_value: int | None
    confidence: float
    pickup_popup: bool = False
    bonus_popup: bool = False


@dataclass
class KillGroup:
    session_id: int
    timestamp_s: float
    group_size: int
    timer_before_s: float
    timer_after_s: float
    elapsed_s: float
    confidence: float


@dataclass
class KillLabel:
    kind: LabelKind
    n_bonus: int
    n_bullet: int
    confidence: float


@dataclass
class ClipRecord:
    clip_path: str
    label_kind: LabelKind
    n_bonus: int
    n_bullet: int
    source_video: str
    session_id: int
    event_timestamp_s: float
    confidence: float
