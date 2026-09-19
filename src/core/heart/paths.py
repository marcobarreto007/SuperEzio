from __future__ import annotations

from dataclasses import dataclass

ALLOWED_WINDOWS = frozenset({"same_session"})
ALLOWED_AXES = frozenset({"abnormal_return", "gross_return", "lifetime_score", "surprise"})
ALLOWED_STATUS = frozenset({"kept", "killed", "refused_empty_store", "unweighted"})


@dataclass(frozen=True, slots=True)
class PathSpec:
    event_type: str
    window: str
    axis: str

    def __post_init__(self) -> None:
        if self.window not in ALLOWED_WINDOWS:
            raise ValueError(f"unsupported window: {self.window}")
        if self.axis not in ALLOWED_AXES:
            raise ValueError(f"unsupported axis: {self.axis}")

    @property
    def path_id(self) -> str:
        return f"{self.event_type}|{self.window}|{self.axis}"


@dataclass(frozen=True, slots=True)
class PathDecision:
    path_id: str
    status: str
    weight: float

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_STATUS:
            raise ValueError(f"unsupported status: {self.status}")
        if self.weight < 0:
            raise ValueError("weight must be >= 0")
        if self.status in ("killed", "refused_empty_store", "unweighted") and self.weight != 0.0:
            raise ValueError(f"{self.status} paths must have weight 0.0")


SPINE_PATH = PathSpec(
    event_type="nyse.luld_pause",
    window="same_session",
    axis="gross_return",
)
