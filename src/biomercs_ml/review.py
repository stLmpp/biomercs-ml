from dataclasses import dataclass, field


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
