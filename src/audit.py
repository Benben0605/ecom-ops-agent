from dataclasses import dataclass, asdict
import json
from pathlib import Path

AUDIT_PATH = Path(__file__).parents[1] / "logs" / "audit.jsonl"

@dataclass
class ToolAudit:
    session_id: str
    tool_ok: bool
    tool_name: str
    tool_params: dict
    tool_duration_ms: float
    tool_output: str = ""
    tool_error: str | None = None
    

def record_audit(tool_audit: ToolAudit) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(asdict(tool_audit), ensure_ascii=False)
    with AUDIT_PATH.open("a", encoding="utf-8") as f:
        f.write(raw + "\n")