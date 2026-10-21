from typing import Protocol, Any
from sqlalchemy.orm import Session
from engine.database.models import ProjectRecord


class HistoryFault(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.status = code, status


class CommandStrategy(Protocol):
    def prepare(self, db: Session, project: ProjectRecord, input: dict) -> dict | None: ...
    def validate(self, payload: Any) -> bool: ...
    def apply(self, db: Session, project: ProjectRecord, payload: dict, *, forward: bool) -> None: ...


class CommandRegistry:
    def __init__(self):
        self._strategies: dict[tuple[str, int], CommandStrategy] = {}

    def register(self, command_type: str, version: int, strategy: CommandStrategy):
        key = command_type, version
        if not command_type or type(version) is not int or version < 1 or key in self._strategies:
            raise HistoryFault("VALIDATION", "Invalid or duplicate command registration", 422)
        self._strategies[key] = strategy
        return self

    def resolve(self, command_type: str, version: int) -> CommandStrategy:
        if type(version) is not int or version < 1 or (command_type, version) not in self._strategies:
            raise HistoryFault("COMPATIBILITY", "Unsupported history command version", 422)
        return self._strategies[command_type, version]
