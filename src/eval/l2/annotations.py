from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).parents[3]
ANNOTATION_RELATIVE_PATH = Path("logs") / "l2_root_cause_annotations.jsonl"

ROOT_CAUSE_OPTIONS: list[dict[str, str]] = [
    {
        "value": "agent_hallucination",
        "label": "agent越界，凭空加戏",
        "description": "answer 补充了 tool output 中没有的业务事实、政策或操作结论。",
    },
    {
        "value": "over_inference",
        "label": "过度推导",
        "description": "基于有限工具证据推出了更强、更具体或更确定的结论。",
    },
    {
        "value": "missing_tool_evidence",
        "label": "工具输出缺证据",
        "description": "工具返回内容不足，无法支撑该断言，需要补工具字段或检索覆盖。",
    },
    {
        "value": "stale_or_wrong_policy",
        "label": "知识/规则过期或错误",
        "description": "agent 使用了与当前工具证据不一致的旧规则或错误规则。",
    },
    {
        "value": "judge_false_positive",
        "label": "judge误判",
        "description": "tool output 实际支持该断言，问题在 judge prompt、抽取或裁决。",
    },
    {
        "value": "assertion_extraction_error",
        "label": "断言抽取错误",
        "description": "judge 抽出的断言不等同于 answer 原意，导致错误归红。",
    },
    {
        "value": "golden_or_data_issue",
        "label": "case/golden数据问题",
        "description": "测试 case、golden point 或 mock 数据本身不一致。",
    },
]

ROOT_CAUSE_LABELS = {item["value"]: item["label"] for item in ROOT_CAUSE_OPTIONS}


def annotation_path(root: Path | None = None) -> Path:
    return (root or ROOT) / ANNOTATION_RELATIVE_PATH


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def build_l2_issue_id(case_id: str, verdict: str, assertion: str) -> str:
    raw = "\0".join(
        [
            _normalize_text(case_id),
            _normalize_text(verdict).lower(),
            _normalize_text(assertion),
        ]
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"l2f_{digest}"


def root_cause_label(root_cause: str) -> str:
    return ROOT_CAUSE_LABELS.get(root_cause, root_cause)


def build_l2_root_cause_summary(
    *,
    case_id: str,
    verdict: str,
    assertion: str,
    root_cause: str,
    root_cause_note: str = "",
) -> str:
    label = root_cause_label(root_cause)
    note = root_cause_note.strip()
    cause = f"{label}；说明：{note}" if note else label
    return "\n".join(
        [
            f"{case_id} | L2 忠实轴 | {verdict.upper()}",
            f"断言：“{assertion}”",
            f"根因：{cause}",
        ]
    )


def build_l2_harness_hypothesis(
    *,
    assertion: str,
    root_cause: str,
    root_cause_note: str = "",
) -> str:
    label = root_cause_label(root_cause)
    detail = root_cause_note.strip() or label
    if root_cause == "agent_hallucination":
        return (
            f"假设：Agent 在缺少工具证据时自行补充业务规则，导致断言“{assertion}”"
            "被判 UNSUPPORTED。下一轮 harness 可约束回答只陈述 tool output 支持的事实，"
            "观察该类 UNSUPPORTED 是否消失。"
        )
    if root_cause == "judge_false_positive":
        return (
            f"假设：该失败主要来自 L2 judge 假阳性（{detail}）。下一轮 harness 应优先修正"
            "judge prompt 或 fixture，再复跑确认该断言是否仍为 UNSUPPORTED。"
        )
    return (
        f"假设：{detail}导致 answer 出现无工具证据支持的断言“{assertion}”。"
        "下一轮 harness 可围绕该根因修改 agent/tool/judge，并复跑验证。"
    )


def _normalize_annotation(record: dict[str, Any]) -> dict[str, Any] | None:
    case_id = _normalize_text(record.get("case_id"))
    assertion = _normalize_text(record.get("assertion"))
    verdict = _normalize_text(record.get("verdict") or "unsupported").lower()
    root_cause = _normalize_text(record.get("root_cause"))
    root_cause_note = str(record.get("root_cause_note") or "").strip()

    if not case_id or not assertion or not root_cause:
        return None
    if verdict != "unsupported":
        return None

    issue_id = build_l2_issue_id(case_id, verdict, assertion)
    updated_at = (
        str(record.get("updated_at") or record.get("created_at") or "").strip()
        or datetime.now().astimezone().isoformat(timespec="seconds")
    )

    normalized = {
        "issue_id": issue_id,
        "level": "L2",
        "axis": "faithfulness",
        "case_id": case_id,
        "verdict": verdict,
        "assertion": assertion,
        "root_cause": root_cause,
        "root_cause_label": root_cause_label(root_cause),
        "root_cause_note": root_cause_note,
        "updated_at": updated_at,
    }
    normalized["summary"] = build_l2_root_cause_summary(
        case_id=case_id,
        verdict=verdict,
        assertion=assertion,
        root_cause=root_cause,
        root_cause_note=root_cause_note,
    )
    normalized["hypothesis"] = build_l2_harness_hypothesis(
        assertion=assertion,
        root_cause=root_cause,
        root_cause_note=root_cause_note,
    )
    return normalized


def load_latest_l2_annotations(root: Path | None = None) -> dict[str, dict[str, Any]]:
    path = annotation_path(root)
    if not path.exists():
        return {}

    latest: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            raw = line.strip()
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            annotation = _normalize_annotation(parsed)
            if annotation:
                latest[annotation["issue_id"]] = annotation
    return latest


def save_l2_annotation(payload: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    record = {
        **payload,
        "updated_at": timestamp,
    }
    annotation = _normalize_annotation(record)
    if not annotation:
        raise ValueError("只支持为 L2 忠实轴 UNSUPPORTED 断言保存非空根因。")

    path = annotation_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(annotation, ensure_ascii=False) + "\n")

    return annotation
