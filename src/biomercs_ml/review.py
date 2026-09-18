import re
from dataclasses import dataclass, field

_CORRECTION_PATTERN = re.compile(r"(\d+)/(\d+)")


@dataclass
class ReviewAnswer:
    outcome: str  # "y", "n", or "skip"
    true_n_bonus: int | None = None
    true_n_bullet: int | None = None


def parse_review_answer(answer: str) -> ReviewAnswer:
    answer = answer.strip().lower()
    if answer == "y":
        return ReviewAnswer(outcome="y")
    if answer == "n":
        return ReviewAnswer(outcome="n")
    match = _CORRECTION_PATTERN.fullmatch(answer)
    if match:
        return ReviewAnswer(
            outcome="n", true_n_bonus=int(match.group(1)), true_n_bullet=int(match.group(2))
        )
    return ReviewAnswer(outcome="skip")


@dataclass
class ReviewTally:
    history: list[str] = field(default_factory=list)

    def record(self, outcome: str) -> None:
        self.history.append(outcome)

    def undo_last(self) -> str | None:
        if not self.history:
            return None
        return self.history.pop()

    @property
    def correct(self) -> int:
        return self.history.count("y")

    @property
    def incorrect(self) -> int:
        return self.history.count("n")

    @property
    def skipped(self) -> int:
        return self.history.count("skip")
