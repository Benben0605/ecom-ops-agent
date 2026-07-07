from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from src.dashboard.experiment_adapter import build_l2_experiment_dashboard_data
from src.eval.l2.annotations import (
    ROOT_CAUSE_OPTIONS,
    annotation_path,
    build_l2_issue_id,
    load_latest_l2_annotations,
)


ROOT = Path(__file__).parents[3]


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[Any]:
    if not path.exists():
        return []

    records: list[Any] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            raw = line.strip()
            if raw:
                records.append(json.loads(raw))
    return records


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _empty_bucket() -> dict[str, int]:
    return {
        "case_count": 0,
        "passed_case_count": 0,
        "issue_case_count": 0,
        "hit_issue_case_count": 0,
        "faith_issue_case_count": 0,
        "hit_ok": 0,
        "hit_total": 0,
        "faith_ok": 0,
        "faith_total": 0,
    }


def _finalize_stats(stats: dict[str, Any]) -> dict[str, Any]:
    return {
        **stats,
        "case_pass_rate": _rate(stats["passed_case_count"], stats["case_count"]),
        "hit_rate": _rate(stats["hit_ok"], stats["hit_total"]),
        "faithfulness_rate": _rate(stats["faith_ok"], stats["faith_total"]),
    }


def _source_context(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, list[Any]]]:
    """Load source data used to backfill older L2 result files.

    New result files persist the complete five-part input. Older files only contain
    question, answer and bucket, so the dashboard reconstructs golden points and
    the tool-output pool from the same files used by eval_l2_judge.
    """
    eval_cases = _load_json(root / "data" / "eval_cases.json", [])
    cases_by_id = {
        item["id"]: item
        for item in eval_cases
        if isinstance(item, dict) and item.get("id")
    }

    run_map = _load_json(root / "logs" / "run_map.json", [])
    session_by_case = {
        item["case_id"]: item["session_id"]
        for item in run_map
        if isinstance(item, dict) and item.get("case_id") and item.get("session_id")
    }
    messages_by_session = {
        item["session_id"]: item["messages"]
        for item in _load_jsonl(root / "logs" / "session_messages.jsonl")
        if isinstance(item, dict)
        and item.get("session_id")
        and isinstance(item.get("messages"), list)
    }
    tool_outputs_by_case: dict[str, list[Any]] = {}
    for case_id, session_id in session_by_case.items():
        messages = messages_by_session.get(session_id, [])
        tool_outputs_by_case[case_id] = [
            message.get("content")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "tool"
        ]

    return cases_by_id, tool_outputs_by_case


def build_l2_dashboard_data(
    root: Path | None = None,
    exp_id: str | None = None,
    variant: str | None = None,
) -> dict[str, Any]:
    root = root or ROOT
    if exp_id or variant:
        if not exp_id or not variant:
            raise ValueError("读取 experiment dashboard 需要同时提供 exp_id 和 variant")
        return build_l2_experiment_dashboard_data(
            root=root,
            exp_id=exp_id,
            variant=variant,
        )

    result_path = root / "logs" / "l2_eval_result.json"
    raw_results = _load_json(result_path, {})
    if not isinstance(raw_results, dict):
        raw_results = {}

    cases_by_id, tool_outputs_by_case = _source_context(root)
    annotations = load_latest_l2_annotations(root)
    annotations_path = annotation_path(root)
    rows: list[dict[str, Any]] = []
    totals = _empty_bucket()
    bucket_stats: dict[str, dict[str, int]] = defaultdict(_empty_bucket)

    for case_id, raw in raw_results.items():
        if not isinstance(raw, dict):
            continue

        source_case = cases_by_id.get(case_id, {})
        verdict = raw.get("verdict") if isinstance(raw.get("verdict"), dict) else {}
        hit_axis = [
            item for item in verdict.get("hit_axis", []) if isinstance(item, dict)
        ]
        faithfulness_axis = []
        for item in verdict.get("faithfulness_axis", []):
            if not isinstance(item, dict):
                continue
            axis_item = dict(item)
            assertion = str(axis_item.get("assertion") or "")
            axis_verdict = str(axis_item.get("verdict") or "").lower()
            issue_id = build_l2_issue_id(case_id, axis_verdict, assertion)
            axis_item["assertion"] = assertion
            axis_item["verdict"] = axis_verdict
            axis_item["issue_id"] = issue_id
            annotation = annotations.get(issue_id)
            if annotation:
                axis_item["annotation"] = annotation
            faithfulness_axis.append(axis_item)

        hit_ok = sum(item.get("verdict") == "hit" for item in hit_axis)
        faith_ok = sum(
            item.get("verdict") == "supported" for item in faithfulness_axis
        )
        miss_count = sum(item.get("verdict") == "miss" for item in hit_axis)
        unsupported_count = sum(
            item.get("verdict") == "unsupported" for item in faithfulness_axis
        )
        annotation_count = sum(
            1 for item in faithfulness_axis if item.get("annotation")
        )
        has_hit_issue = miss_count > 0
        has_faith_issue = unsupported_count > 0
        has_issue = has_hit_issue or has_faith_issue

        golden_points = raw.get("golden_points")
        if not isinstance(golden_points, list):
            golden_points = source_case.get("golden_answer_points")
        if not isinstance(golden_points, list):
            golden_points = [item.get("point", "") for item in hit_axis]

        tool_outputs = raw.get("tool_outputs")
        if not isinstance(tool_outputs, list):
            tool_outputs = tool_outputs_by_case.get(case_id, [])

        row = {
            "case_id": case_id,
            "bucket": raw.get("bucket") or source_case.get("bucket") or "unknown",
            "question": raw.get("question") or source_case.get("question") or "",
            "answer": raw.get("answer") or "",
            "tool_outputs": tool_outputs,
            "golden_points": golden_points,
            "hit_axis": hit_axis,
            "faithfulness_axis": faithfulness_axis,
            "score": {
                "hit_ok": hit_ok,
                "hit_total": len(hit_axis),
                "hit_rate": _rate(hit_ok, len(hit_axis)),
                "faith_ok": faith_ok,
                "faith_total": len(faithfulness_axis),
                "faithfulness_rate": _rate(faith_ok, len(faithfulness_axis)),
            },
            "miss_count": miss_count,
            "unsupported_count": unsupported_count,
            "annotation_count": annotation_count,
            "has_hit_issue": has_hit_issue,
            "has_faith_issue": has_faith_issue,
            "has_issue": has_issue,
            "issue_types": [
                issue
                for issue, present in (
                    ("miss", has_hit_issue),
                    ("unsupported", has_faith_issue),
                )
                if present
            ],
        }
        rows.append(row)

        for stats in (totals, bucket_stats[row["bucket"]]):
            stats["case_count"] += 1
            stats["passed_case_count"] += int(not has_issue)
            stats["issue_case_count"] += int(has_issue)
            stats["hit_issue_case_count"] += int(has_hit_issue)
            stats["faith_issue_case_count"] += int(has_faith_issue)
            stats["hit_ok"] += hit_ok
            stats["hit_total"] += len(hit_axis)
            stats["faith_ok"] += faith_ok
            stats["faith_total"] += len(faithfulness_axis)

    rows.sort(key=lambda row: (not row["has_issue"], row["case_id"]))
    modified_at = (
        datetime.fromtimestamp(result_path.stat().st_mtime)
        .astimezone()
        .isoformat(timespec="seconds")
        if result_path.exists()
        else None
    )

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "context": {
            "mode": "legacy",
            "warnings": [],
        },
        "source": {
            "path": str(result_path),
            "exists": result_path.exists(),
            "modified_at": modified_at,
        },
        "metrics": _finalize_stats(totals),
        "breakdowns": {
            "by_bucket": [
                {"bucket": bucket, **_finalize_stats(stats)}
                for bucket, stats in sorted(bucket_stats.items())
            ]
        },
        "annotations": {
            "path": str(annotations_path),
            "exists": annotations_path.exists(),
            "count": len(annotations),
            "root_cause_options": ROOT_CAUSE_OPTIONS,
        },
        "cases": rows,
        "issue_cases": [row for row in rows if row["has_issue"]],
    }
