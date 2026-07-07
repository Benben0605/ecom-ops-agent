from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from src.dashboard.experiment_adapter import build_l1_experiment_dashboard_data


ROOT = Path(__file__).parents[2]


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[Any]:
    if not path.exists():
        return []

    records: list[Any] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                records.append(
                    {
                        "_parse_error": str(exc),
                        "_line_no": line_no,
                        "_raw": raw,
                    }
                )
    return records


def _tool_names_from_expected(expected_calls: list[dict[str, Any]]) -> list[str]:
    return [
        call["tool_name"]
        for call in expected_calls
        if isinstance(call, dict) and call.get("tool_name")
    ]


def _counter_diff(left: Counter, right: Counter) -> list[str]:
    diff: list[str] = []
    for tool_name, count in (left - right).items():
        diff.extend([tool_name] * count)
    return diff


def _last_assistant_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "assistant" and message.get("content"):
            return message["content"]
    return ""


def _index_session_messages(
    records: list[Any],
) -> tuple[dict[str, list[dict[str, Any]]], list[list[dict[str, Any]]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    unwrapped: list[list[dict[str, Any]]] = []
    for record in records:
        if isinstance(record, dict) and isinstance(record.get("messages"), list):
            session_id = record.get("session_id")
            if session_id:
                indexed[session_id] = record["messages"]
            continue

        # Backward compatibility for per_case_run, which used to write the
        # messages list directly without wrapping session_id.
        if isinstance(record, list):
            unwrapped.append(record)
    return indexed, unwrapped


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0


def _empty_bucket() -> dict[str, Any]:
    return {
        "case_count": 0,
        "evaluated_case_count": 0,
        "positive_case_count": 0,
        "route_hit_count": 0,
        "route_error_count": 0,
        "misfire_count": 0,
        "routing_accuracy": 0,
        "misfire_rate": 0,
    }


def _finalize_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    bucket["routing_accuracy"] = _rate(
        bucket["route_hit_count"], bucket["positive_case_count"]
    )
    bucket["misfire_rate"] = _rate(
        bucket["misfire_count"], bucket["evaluated_case_count"]
    )
    return bucket


def build_dashboard_data(
    root: Path | None = None,
    exp_id: str | None = None,
    variant: str | None = None,
) -> dict[str, Any]:
    root = root or ROOT
    if exp_id or variant:
        if not exp_id or not variant:
            raise ValueError("读取 experiment dashboard 需要同时提供 exp_id 和 variant")
        return build_l1_experiment_dashboard_data(
            root=root,
            exp_id=exp_id,
            variant=variant,
        )

    data_dir = root / "data"
    logs_dir = root / "logs"

    paths = {
        "eval_cases": data_dir / "eval_cases.json",
        "audit": logs_dir / "audit.jsonl",
        "case_eval_result": logs_dir / "case_eval_result.json",
        "run_map": logs_dir / "run_map.json",
        "session_messages": logs_dir / "session_messages.jsonl",
        "eval_metrics": logs_dir / "eval_metrics.json",
    }

    eval_cases: list[dict[str, Any]] = _load_json(paths["eval_cases"], [])
    run_map: list[dict[str, Any]] = _load_json(paths["run_map"], [])
    case_eval_result: dict[str, dict[str, Any]] = _load_json(
        paths["case_eval_result"], {}
    )
    persisted_metrics: dict[str, Any] = _load_json(paths["eval_metrics"], {})
    audit_records: list[dict[str, Any]] = _load_jsonl(paths["audit"])
    message_records = _load_jsonl(paths["session_messages"])

    sessions_by_case: dict[str, list[str]] = defaultdict(list)
    for item in run_map:
        case_id = item.get("case_id")
        session_id = item.get("session_id")
        if case_id and session_id:
            sessions_by_case[case_id].append(session_id)

    audits_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for audit in audit_records:
        if not isinstance(audit, dict):
            continue
        session_id = audit.get("session_id")
        if session_id:
            audits_by_session[session_id].append(audit)

    messages_by_session, unwrapped_messages = _index_session_messages(message_records)
    if unwrapped_messages and run_map:
        recent_unwrapped = unwrapped_messages[-len(run_map) :]
        for index, item in enumerate(run_map[-len(recent_unwrapped) :]):
            session_id = item.get("session_id")
            if session_id and session_id not in messages_by_session:
                messages_by_session[session_id] = recent_unwrapped[index]

    rows: list[dict[str, Any]] = []
    bucket_stats: dict[str, dict[str, Any]] = defaultdict(_empty_bucket)
    expected_tool_stats: dict[str, dict[str, Any]] = defaultdict(_empty_bucket)
    actual_tool_counts: Counter = Counter()

    evaluated_case_count = 0
    positive_case_count = 0
    route_hit_count = 0
    route_error_count = 0
    misfire_count = 0

    for case in eval_cases:
        case_id = case.get("id", "")
        expected_calls = case.get("expected_calls") or []
        expected_tools = _tool_names_from_expected(expected_calls)
        result = case_eval_result.get(case_id)
        session_ids = sessions_by_case.get(case_id, [])
        audits = [
            audit
            for session_id in session_ids
            for audit in audits_by_session.get(session_id, [])
        ]
        fallback_called_tools = [
            audit["tool_name"] for audit in audits if audit.get("tool_name")
        ]
        called_tools = (
            result.get("called_tools", fallback_called_tools)
            if result
            else fallback_called_tools
        )
        called_tools = [tool for tool in called_tools if tool]

        expected_counter = Counter(expected_tools)
        actual_counter = Counter(called_tools)
        missing_tools = (
            result.get("missing_tools")
            if result and "missing_tools" in result
            else _counter_diff(expected_counter, actual_counter)
        )
        unexpected_tools = (
            result.get("unexpected_tools")
            if result and "unexpected_tools" in result
            else _counter_diff(actual_counter, expected_counter)
        )

        is_hit = result.get("is_hit") if result else None
        is_misfire = bool(result.get("is_misfire")) if result else False
        evaluated = result is not None
        route_error = evaluated and bool(expected_tools) and is_hit is False
        not_run = not evaluated

        if evaluated:
            evaluated_case_count += 1
            if expected_tools:
                positive_case_count += 1
                if is_hit:
                    route_hit_count += 1
                else:
                    route_error_count += 1
            if is_misfire:
                misfire_count += 1

        issue_types: list[str] = []
        if not_run:
            issue_types.append("not_run")
        if route_error:
            issue_types.append("route_error")
        if is_misfire:
            issue_types.append("misfire")

        bucket = case.get("bucket", "unknown")
        bucket_item = bucket_stats[bucket]
        bucket_item["case_count"] += 1
        if evaluated:
            bucket_item["evaluated_case_count"] += 1
        if expected_tools:
            bucket_item["positive_case_count"] += 1
            if evaluated and is_hit:
                bucket_item["route_hit_count"] += 1
            if route_error:
                bucket_item["route_error_count"] += 1
        if is_misfire:
            bucket_item["misfire_count"] += 1

        for expected_tool in set(expected_tools):
            tool_item = expected_tool_stats[expected_tool]
            tool_item["case_count"] += 1
            tool_item["positive_case_count"] += 1
            if evaluated:
                tool_item["evaluated_case_count"] += 1
            if evaluated and is_hit:
                tool_item["route_hit_count"] += 1
            if route_error:
                tool_item["route_error_count"] += 1
            if is_misfire:
                tool_item["misfire_count"] += 1

        actual_tool_counts.update(called_tools)

        messages_by_case = {
            session_id: messages_by_session.get(session_id, [])
            for session_id in session_ids
        }
        all_messages = [
            message
            for session_id in session_ids
            for message in messages_by_session.get(session_id, [])
        ]

        rows.append(
            {
                "case_id": case_id,
                "bucket": bucket,
                "question": case.get("question", ""),
                "trap": case.get("trap", ""),
                "clarify": bool(case.get("clarify")),
                "should_call_tool": bool(case.get("should_call_tool")),
                "expected_calls": expected_calls,
                "expected_tools": expected_tools,
                "called_tools": called_tools,
                "missing_tools": missing_tools,
                "unexpected_tools": unexpected_tools,
                "is_hit": is_hit,
                "is_misfire": is_misfire,
                "route_error": route_error,
                "not_run": not_run,
                "issue_types": issue_types,
                "session_ids": session_ids,
                "audit_count": len(audits),
                "tool_error_count": len([a for a in audits if a.get("tool_error")]),
                "tool_duration_ms": round(
                    sum(float(a.get("tool_duration_ms") or 0) for a in audits), 2
                ),
                "last_assistant_message": _last_assistant_text(all_messages),
                "audits": audits,
                "messages_by_session": messages_by_case,
            }
        )

    bucket_breakdown = [
        {"bucket": bucket, **_finalize_bucket(stats)}
        for bucket, stats in sorted(bucket_stats.items())
    ]
    expected_tool_breakdown = [
        {"tool_name": tool_name, **_finalize_bucket(stats)}
        for tool_name, stats in sorted(expected_tool_stats.items())
    ]
    actual_tool_breakdown = [
        {"tool_name": tool_name, "call_count": count}
        for tool_name, count in actual_tool_counts.most_common()
    ]

    metrics = {
        "case_count": len(eval_cases),
        "evaluated_case_count": evaluated_case_count,
        "coverage_rate": _rate(evaluated_case_count, len(eval_cases)),
        "positive_case_count": positive_case_count,
        "route_hit_count": route_hit_count,
        "route_error_count": route_error_count,
        "routing_accuracy": _rate(route_hit_count, positive_case_count),
        "misfire_count": misfire_count,
        "misfire_rate": _rate(misfire_count, evaluated_case_count),
        "failure_case_count": len(
            [row for row in rows if row["route_error"] or row["is_misfire"]]
        ),
    }

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "context": {
            "mode": "legacy",
            "warnings": [],
        },
        "paths": {name: str(path) for name, path in paths.items()},
        "metrics": metrics,
        "persisted_metrics": persisted_metrics,
        "breakdowns": {
            "by_bucket": bucket_breakdown,
            "by_expected_tool": expected_tool_breakdown,
            "actual_tool_calls": actual_tool_breakdown,
        },
        "cases": rows,
        "route_error_cases": [row for row in rows if row["route_error"]],
        "misfire_cases": [row for row in rows if row["is_misfire"]],
    }
