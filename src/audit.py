import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass
class ToolAudit:
    session_id: str
    has_tool_call: bool
    tool_name: str
    tool_params: str | dict[str, Any]
    tool_duration_ms: float
    tool_output: str = ""
    tool_error: str | None = None


DEFAULT_AUDIT_RECORDER_PATH = Path(__file__).parents[1] / "logs" / "audit.jsonl"
DEFAULT_MESSAGES_RECORDER_PATH = (
    Path(__file__).parents[1] / "logs" / "session_messages.jsonl"
)


class AuditRecorder:
    def __init__(self, recorder_path: Path | None = None):
        self.recorder_path = recorder_path or DEFAULT_AUDIT_RECORDER_PATH

    def record(self, tool_audit: ToolAudit) -> None:
        """
        工具级审计
        """
        self.recorder_path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(asdict(tool_audit), ensure_ascii=False)
        with self.recorder_path.open("a", encoding="utf-8") as f:
            f.write(raw + "\n")


class NoOpRecorder:
    """空记录器：supervisor 的 agent-as-tool dispatch 不进审计流（只记叶子业务工具）。"""

    def record(self, tool_audit: ToolAudit) -> None:
        pass


class ToolAuditRecorder(Protocol):
    def record(self, tool_audit: ToolAudit) -> None: ...


class MessageRecorder:
    def __init__(self, recorder_path: Path | None = None):
        self.recorder_path = recorder_path or DEFAULT_MESSAGES_RECORDER_PATH

    def record(self, session_messages: dict[str, Any]) -> None:
        """
        会话级审计
        """
        self.recorder_path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(session_messages, ensure_ascii=False)
        with self.recorder_path.open("a", encoding="utf-8") as f:
            f.write(raw + "\n")


class SessionMessageRecorder(Protocol):
    def record(self, session_messages: dict[str, Any]) -> None: ...
