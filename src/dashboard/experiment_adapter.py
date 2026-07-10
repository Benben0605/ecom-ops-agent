from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from src.eval.l2.annotations import (
    ROOT_CAUSE_OPTIONS,
    annotation_path,
    build_l2_issue_id,
    load_latest_l2_annotations,
)


ROOT = Path(__file__).parents[2]
EXPERIMENTS_ROOT = ROOT / "logs" / "experiments"


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[Any]:
    if not path.exists():
        return []

    records: list[Any] = []
    with path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                records.append(
                    {"_parse_error": str(exc), "_line_no": line_no, "_raw": raw}
                )
    return records


def _rate(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0


def _nullable_rate(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _clean_number(value: float) -> int | float:
    if float(value).is_integer():
        return int(value)
    return round(value, 4)


def _ordered_unique(values: list[Any]) -> list[Any]:
    seen = set()
    out = []
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _last_assistant_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "assistant" and message.get("content"):
            return str(message["content"])
    return ""


def _load_eval_cases(root: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    cases = _load_json(root / "data" / "eval_cases.json", [])
    if not isinstance(cases, list):
        cases = []
    by_id = {
        item["id"]: item
        for item in cases
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    return cases, by_id


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _modified_at(path: Path) -> str | None:
    if not path.exists():
        return None
    return (
        datetime.fromtimestamp(path.stat().st_mtime)
        .astimezone()
        .isoformat(timespec="seconds")
    )


def _experiment_paths(root: Path, exp_id: str, variant: str) -> tuple[Path, Path, Path]:
    exp_dir = root / "logs" / "experiments" / exp_id
    manifest_path = exp_dir / "manifest.json"
    variant_dir = exp_dir / "variants" / variant
    if not manifest_path.exists():
        raise FileNotFoundError(f"实验不存在：{exp_id}")
    if not variant_dir.exists():
        raise FileNotFoundError(f"实验变体不存在：{exp_id}/{variant}")
    return exp_dir, manifest_path, variant_dir


def _context(
    *,
    root: Path,
    manifest: dict[str, Any],
    exp_id: str,
    variant: str,
    source_paths: list[Path],
    dataset_key: str = "eval_cases",
    dataset_rel: str = "data/eval_cases.json",
    drift_hint: str = "case 文案和 golden 回填可能与历史运行时不同。",
) -> dict[str, Any]:
    manifest_sha = (
        manifest.get("provenance", {})
        .get("dataset_sha", {})
        .get(dataset_key)
    )
    current_sha = _sha256(root / dataset_rel)
    warnings: list[str] = []
    dataset_sha_match: bool | None = None
    if manifest_sha and current_sha:
        dataset_sha_match = manifest_sha == current_sha
        if not dataset_sha_match:
            warnings.append(
                f"当前 {dataset_rel} 与该实验记录的 dataset_sha 不一致，{drift_hint}"
            )

    modified_values = [value for value in (_modified_at(path) for path in source_paths) if value]
    return {
        "mode": "experiment",
        "exp_id": exp_id,
        "experiment_name": manifest.get("name", exp_id),
        "variant": variant,
        "track": manifest.get("track"),
        "n": manifest.get("provenance", {}).get("n"),
        "provenance": manifest.get("provenance", {}),
        "dataset_sha_match": dataset_sha_match,
        "dataset_sha_manifest": manifest_sha,
        "dataset_sha_current": current_sha,
        "warnings": warnings,
        "source_paths": [str(path) for path in source_paths],
        "source_modified_at": max(modified_values) if modified_values else None,
    }


def _trace_run_dirs(trace_dir: Path) -> list[tuple[int, Path]]:
    if (trace_dir / "run_map.json").exists():
        return [(1, trace_dir)]

    run_dirs: list[tuple[int, Path]] = []
    if not trace_dir.exists():
        return run_dirs
    for child in trace_dir.iterdir():
        if not child.is_dir() or not (child / "run_map.json").exists():
            continue
        index = len(run_dirs) + 1
        if child.name.startswith("run_"):
            try:
                index = int(child.name.removeprefix("run_"))
            except ValueError:
                pass
        run_dirs.append((index, child))
    return sorted(run_dirs, key=lambda item: item[0])


def _messages_by_session(records: list[Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        session_id = record.get("session_id")
        messages = record.get("messages")
        if session_id and isinstance(messages, list):
            out[str(session_id)] = [
                item for item in messages if isinstance(item, dict)
            ]
    return out


def _load_trace_by_case(variant_dir: Path) -> dict[str, list[dict[str, Any]]]:
    traces: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run_index, run_dir in _trace_run_dirs(variant_dir / "trace"):
        run_map = _load_json(run_dir / "run_map.json", [])
        if not isinstance(run_map, list):
            continue
        audits_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for audit in _load_jsonl(run_dir / "audit.jsonl"):
            if not isinstance(audit, dict):
                continue
            session_id = audit.get("session_id")
            if session_id:
                audits_by_session[str(session_id)].append(audit)
        messages = _messages_by_session(_load_jsonl(run_dir / "session_messages.jsonl"))

        for item in run_map:
            if not isinstance(item, dict):
                continue
            case_id = item.get("case_id")
            session_id = item.get("session_id")
            if not case_id or not session_id:
                continue
            session_id = str(session_id)
            session_messages = messages.get(session_id, [])
            traces[str(case_id)].append(
                {
                    "run_index": run_index,
                    "run_dir": str(run_dir),
                    "session_id": session_id,
                    "audits": audits_by_session.get(session_id, []),
                    "messages": session_messages,
                    "tool_outputs": [
                        message.get("content")
                        for message in session_messages
                        if message.get("role") == "tool"
                    ],
                    "last_assistant_message": _last_assistant_text(session_messages),
                }
            )
    return traces


def _expected_calls_from_source(
    source_case: dict[str, Any],
    expected_tools: list[str],
) -> list[dict[str, Any]]:
    expected_calls = source_case.get("expected_calls")
    if isinstance(expected_calls, list):
        return [item for item in expected_calls if isinstance(item, dict)]
    return [{"tool_name": tool_name, "tool_params": {}} for tool_name in expected_tools]


def _l1_raw_runs(raw: dict[str, Any]) -> list[dict[str, Any]]:
    runs = raw.get("runs")
    if isinstance(runs, list) and runs:
        return [item for item in runs if isinstance(item, dict)]
    return [
        {
            "called_tools": raw.get("called_tools", []),
            "missing_tools": raw.get("missing_tools", []),
            "unexpected_tools": raw.get("unexpected_tools", []),
            "is_hit": raw.get("is_hit"),
            "is_misfire": raw.get("is_misfire"),
        }
    ]


def _trace_for_run(
    traces: list[dict[str, Any]],
    run_index: int,
    position: int,
) -> dict[str, Any]:
    for trace in traces:
        if trace.get("run_index") == run_index:
            return trace
    return traces[position] if position < len(traces) else {}


def _empty_l1_bucket() -> dict[str, float]:
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


def _finalize_l1_bucket(stats: dict[str, float]) -> dict[str, Any]:
    stats["routing_accuracy"] = _rate(
        stats["route_hit_count"], stats["positive_case_count"]
    )
    stats["misfire_rate"] = _rate(
        stats["misfire_count"], stats["evaluated_case_count"]
    )
    return {key: _clean_number(value) for key, value in stats.items()}


def build_l1_experiment_dashboard_data(
    *,
    root: Path | None = None,
    exp_id: str,
    variant: str,
) -> dict[str, Any]:
    root = root or ROOT
    _, manifest_path, variant_dir = _experiment_paths(root, exp_id, variant)
    manifest = _load_json(manifest_path, {})
    if manifest.get("track") != "agent":
        raise ValueError("只有 agent track 实验支持 L1/L2 Dashboard")

    result_path = variant_dir / "eval" / "l1_case_result.json"
    metrics_path = variant_dir / "eval" / "l1_metrics.json"
    raw_results = _load_json(result_path, {})
    if not isinstance(raw_results, dict):
        raw_results = {}
    traces_by_case = _load_trace_by_case(variant_dir)
    _, cases_by_id = _load_eval_cases(root)

    rows: list[dict[str, Any]] = []
    bucket_stats: dict[str, dict[str, float]] = defaultdict(_empty_l1_bucket)
    tool_stats: dict[str, dict[str, float]] = defaultdict(_empty_l1_bucket)
    actual_tool_counts: Counter[str] = Counter()
    total_stats = _empty_l1_bucket()

    for case_id in sorted(raw_results):
        raw = raw_results[case_id]
        if not isinstance(raw, dict):
            continue
        source_case = cases_by_id.get(case_id, {})
        expected_tools = raw.get("spec_tool")
        if not isinstance(expected_tools, list):
            expected_tools = [
                call.get("tool_name")
                for call in source_case.get("expected_calls", [])
                if isinstance(call, dict) and call.get("tool_name")
            ]
        expected_tools = [str(tool) for tool in expected_tools if tool]
        expected_calls = _expected_calls_from_source(source_case, expected_tools)
        positive = bool(expected_tools)
        raw_runs = _l1_raw_runs(raw)
        traces = traces_by_case.get(case_id, [])
        n = int(raw.get("n") or len(raw_runs) or len(traces) or 1)

        experiment_runs: list[dict[str, Any]] = []
        hit_runs = 0
        misfire_runs = 0
        pass_runs = 0
        flattened_called: list[str] = []
        flattened_missing: list[str] = []
        flattened_unexpected: list[str] = []
        combined_audits: list[dict[str, Any]] = []
        messages_by_session: dict[str, list[dict[str, Any]]] = {}
        session_ids: list[str] = []

        for position, run in enumerate(raw_runs):
            run_index = position + 1
            trace = _trace_for_run(traces, run_index, position)
            called_tools = [
                str(tool) for tool in run.get("called_tools", []) if tool
            ]
            missing_tools = [
                str(tool) for tool in run.get("missing_tools", []) if tool
            ]
            unexpected_tools = [
                str(tool) for tool in run.get("unexpected_tools", []) if tool
            ]
            is_hit = run.get("is_hit")
            is_misfire = bool(run.get("is_misfire"))
            passed = (bool(is_hit) and not is_misfire) if positive else not is_misfire

            hit_runs += int(bool(is_hit))
            misfire_runs += int(is_misfire)
            pass_runs += int(passed)
            flattened_called.extend(called_tools)
            flattened_missing.extend(missing_tools)
            flattened_unexpected.extend(unexpected_tools)
            actual_tool_counts.update(called_tools)

            audits = trace.get("audits", [])
            messages = trace.get("messages", [])
            combined_audits.extend(audits)
            session_id = trace.get("session_id")
            session_key = f"run_{run_index}"
            if session_id:
                session_key = f"run_{run_index} · {session_id}"
                session_ids.append(session_key)
                messages_by_session[session_key] = messages

            experiment_runs.append(
                {
                    "run_index": run_index,
                    "session_id": session_id,
                    "called_tools": called_tools,
                    "missing_tools": missing_tools,
                    "unexpected_tools": unexpected_tools,
                    "is_hit": is_hit,
                    "is_misfire": is_misfire,
                    "passed": passed,
                    "audits": audits,
                    "messages": messages,
                    "last_assistant_message": trace.get("last_assistant_message", ""),
                }
            )

        hit_rate = (
            raw.get("hit_rate")
            if isinstance(raw.get("hit_rate"), (int, float))
            else (_rate(hit_runs, len(raw_runs)) if positive else None)
        )
        misfire_rate = (
            raw.get("misfire_rate")
            if isinstance(raw.get("misfire_rate"), (int, float))
            else _rate(misfire_runs, len(raw_runs))
        )
        pass_rate = (
            raw.get("pass_rate")
            if isinstance(raw.get("pass_rate"), (int, float))
            else _rate(pass_runs, len(raw_runs))
        )
        route_error = positive and (hit_rate is None or hit_rate < 1)
        is_misfire = misfire_rate > 0
        issue_types = [
            issue
            for issue, present in (
                ("route_error", route_error),
                ("misfire", is_misfire),
            )
            if present
        ]
        bucket = str(raw.get("bucket") or source_case.get("bucket") or "unknown")

        row = {
            "case_id": case_id,
            "bucket": bucket,
            "question": source_case.get("question") or raw.get("question") or "",
            "trap": source_case.get("trap", ""),
            "clarify": bool(source_case.get("clarify")),
            "should_call_tool": positive,
            "expected_calls": expected_calls,
            "expected_tools": expected_tools,
            "called_tools": _ordered_unique(flattened_called),
            "missing_tools": _ordered_unique(flattened_missing),
            "unexpected_tools": _ordered_unique(flattened_unexpected),
            "is_hit": (hit_rate == 1) if positive else None,
            "is_misfire": is_misfire,
            "route_error": route_error,
            "not_run": False,
            "issue_types": issue_types,
            "session_ids": session_ids,
            "audit_count": len(combined_audits),
            "tool_error_count": len(
                [audit for audit in combined_audits if audit.get("tool_error")]
            ),
            "tool_duration_ms": round(
                sum(float(audit.get("tool_duration_ms") or 0) for audit in combined_audits),
                2,
            ),
            "last_assistant_message": _last_assistant_text(
                [
                    message
                    for trace in traces
                    for message in trace.get("messages", [])
                    if isinstance(message, dict)
                ]
            ),
            "audits": combined_audits,
            "messages_by_session": messages_by_session,
            "n": n,
            "pass_rate": pass_rate,
            "hit_rate": hit_rate,
            "misfire_rate": misfire_rate,
            "experiment_runs": experiment_runs,
        }
        rows.append(row)

        for stats in (total_stats, bucket_stats[bucket]):
            stats["case_count"] += 1
            stats["evaluated_case_count"] += 1
            stats["misfire_count"] += float(misfire_rate or 0)
            if positive:
                stats["positive_case_count"] += 1
                stats["route_hit_count"] += float(hit_rate or 0)
                stats["route_error_count"] += 1 - float(hit_rate or 0)

        for tool_name in set(expected_tools):
            stats = tool_stats[tool_name]
            stats["case_count"] += 1
            stats["evaluated_case_count"] += 1
            stats["positive_case_count"] += 1
            stats["route_hit_count"] += float(hit_rate or 0)
            stats["route_error_count"] += 1 - float(hit_rate or 0)
            stats["misfire_count"] += float(misfire_rate or 0)

    metrics = _finalize_l1_bucket(total_stats)
    metrics["coverage_rate"] = 1 if metrics["case_count"] else 0
    metrics["failure_case_count"] = len(
        [row for row in rows if row["route_error"] or row["is_misfire"]]
    )

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": {
            "path": str(result_path),
            "exists": result_path.exists(),
            "modified_at": _modified_at(result_path),
        },
        "context": _context(
            root=root,
            manifest=manifest,
            exp_id=exp_id,
            variant=variant,
            source_paths=[result_path, metrics_path],
        ),
        "metrics": metrics,
        "persisted_metrics": _load_json(metrics_path, {}),
        "breakdowns": {
            "by_bucket": [
                {"bucket": bucket, **_finalize_l1_bucket(stats)}
                for bucket, stats in sorted(bucket_stats.items())
            ],
            "by_expected_tool": [
                {"tool_name": tool_name, **_finalize_l1_bucket(stats)}
                for tool_name, stats in sorted(tool_stats.items())
            ],
            "actual_tool_calls": [
                {"tool_name": tool_name, "call_count": count}
                for tool_name, count in actual_tool_counts.most_common()
            ],
        },
        "cases": rows,
        "route_error_cases": [row for row in rows if row["route_error"]],
        "misfire_cases": [row for row in rows if row["is_misfire"]],
    }


def _empty_l2_stats() -> dict[str, float]:
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


def _finalize_l2_stats(stats: dict[str, float]) -> dict[str, Any]:
    finalized = {
        **{key: _clean_number(value) for key, value in stats.items()},
        "case_pass_rate": _nullable_rate(
            stats["passed_case_count"], stats["case_count"]
        ),
        "hit_rate": _nullable_rate(stats["hit_ok"], stats["hit_total"]),
        "faithfulness_rate": _nullable_rate(stats["faith_ok"], stats["faith_total"]),
    }
    return finalized


def _l2_passed(raw: dict[str, Any]) -> bool:
    if isinstance(raw.get("passed"), bool):
        return bool(raw["passed"])
    verdict = raw.get("verdict") if isinstance(raw.get("verdict"), dict) else {}
    misses = any(
        item.get("verdict") == "miss"
        for item in verdict.get("hit_axis", [])
        if isinstance(item, dict)
    )
    unsupported = any(
        item.get("verdict") == "unsupported"
        for item in verdict.get("faithfulness_axis", [])
        if isinstance(item, dict)
    )
    return not (misses or unsupported)


def _score_from_verdict(verdict: dict[str, Any]) -> dict[str, Any]:
    hit_axis = [
        item for item in verdict.get("hit_axis", []) if isinstance(item, dict)
    ]
    faithfulness_axis = [
        item
        for item in verdict.get("faithfulness_axis", [])
        if isinstance(item, dict)
    ]
    hit_ok = sum(item.get("verdict") == "hit" for item in hit_axis)
    faith_ok = sum(item.get("verdict") == "supported" for item in faithfulness_axis)
    return {
        "hit_ok": hit_ok,
        "hit_total": len(hit_axis),
        "hit_rate": _nullable_rate(hit_ok, len(hit_axis)),
        "faith_ok": faith_ok,
        "faith_total": len(faithfulness_axis),
        "faithfulness_rate": _nullable_rate(faith_ok, len(faithfulness_axis)),
    }


def _l2_raw_runs(raw: dict[str, Any]) -> list[dict[str, Any]]:
    runs = raw.get("runs")
    if isinstance(runs, list) and runs:
        return [item for item in runs if isinstance(item, dict)]
    if isinstance(raw.get("verdict"), dict):
        return [
            {
                "answer": raw.get("answer", ""),
                "verdict": raw.get("verdict", {}),
                "score": raw.get("score"),
                "passed": _l2_passed(raw),
            }
        ]
    return []


def _normalize_l2_axes(
    *,
    case_id: str,
    exp_id: str,
    variant: str,
    run_index: int,
    verdict: dict[str, Any],
    annotations: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int, int]:
    hit_axis: list[dict[str, Any]] = []
    faithfulness_axis: list[dict[str, Any]] = []
    for item in verdict.get("hit_axis", []):
        if not isinstance(item, dict):
            continue
        axis = dict(item)
        axis["verdict"] = str(axis.get("verdict") or "").lower()
        hit_axis.append(axis)

    annotation_count = 0
    for item in verdict.get("faithfulness_axis", []):
        if not isinstance(item, dict):
            continue
        axis = dict(item)
        assertion = str(axis.get("assertion") or "")
        axis_verdict = str(axis.get("verdict") or "").lower()
        issue_id = build_l2_issue_id(
            case_id,
            axis_verdict,
            assertion,
            exp_id=exp_id,
            variant=variant,
            run_index=run_index,
        )
        axis["assertion"] = assertion
        axis["verdict"] = axis_verdict
        axis["issue_id"] = issue_id
        axis["run_index"] = run_index
        annotation = annotations.get(issue_id)
        if annotation:
            axis["annotation"] = annotation
            annotation_count += 1
        faithfulness_axis.append(axis)

    miss_count = sum(item.get("verdict") == "miss" for item in hit_axis)
    unsupported_count = sum(
        item.get("verdict") == "unsupported" for item in faithfulness_axis
    )
    return hit_axis, faithfulness_axis, miss_count, unsupported_count, annotation_count


def build_l2_experiment_dashboard_data(
    *,
    root: Path | None = None,
    exp_id: str,
    variant: str,
) -> dict[str, Any]:
    root = root or ROOT
    _, manifest_path, variant_dir = _experiment_paths(root, exp_id, variant)
    manifest = _load_json(manifest_path, {})
    if manifest.get("track") != "agent":
        raise ValueError("只有 agent track 实验支持 L1/L2 Dashboard")

    result_path = variant_dir / "eval" / "l2_case_result.json"
    metrics_path = variant_dir / "eval" / "l2_metrics.json"
    raw_results = _load_json(result_path, {})
    if not isinstance(raw_results, dict):
        raw_results = {}
    traces_by_case = _load_trace_by_case(variant_dir)
    _, cases_by_id = _load_eval_cases(root)
    annotations = load_latest_l2_annotations(root)
    annotations_path = annotation_path(root)

    rows: list[dict[str, Any]] = []
    totals = _empty_l2_stats()
    bucket_stats: dict[str, dict[str, float]] = defaultdict(_empty_l2_stats)

    for case_id in sorted(raw_results):
        raw = raw_results[case_id]
        if not isinstance(raw, dict):
            continue
        raw_runs = _l2_raw_runs(raw)
        if not raw_runs:
            continue
        source_case = cases_by_id.get(case_id, {})
        traces = traces_by_case.get(case_id, [])
        bucket = str(raw.get("bucket") or source_case.get("bucket") or "unknown")
        question = raw.get("question") or source_case.get("question") or ""
        golden_points = source_case.get("golden_answer_points")
        if not isinstance(golden_points, list):
            golden_points = []

        experiment_runs: list[dict[str, Any]] = []
        flattened_hit_axis: list[dict[str, Any]] = []
        flattened_faithfulness_axis: list[dict[str, Any]] = []
        flattened_tool_outputs: list[Any] = []
        hit_ok = hit_total = faith_ok = faith_total = 0
        pass_runs = miss_count = unsupported_count = annotation_count = 0

        for position, run in enumerate(raw_runs):
            run_index = position + 1
            trace = _trace_for_run(traces, run_index, position)
            verdict = run.get("verdict") if isinstance(run.get("verdict"), dict) else {}
            score = run.get("score")
            if not isinstance(score, dict):
                score = _score_from_verdict(verdict)
            passed = _l2_passed(run)
            run_hit_axis, run_faith_axis, run_miss, run_unsupported, run_annotations = (
                _normalize_l2_axes(
                    case_id=case_id,
                    exp_id=exp_id,
                    variant=variant,
                    run_index=run_index,
                    verdict=verdict,
                    annotations=annotations,
                )
            )
            run_tool_outputs = run.get("tool_outputs")
            if not isinstance(run_tool_outputs, list):
                run_tool_outputs = trace.get("tool_outputs", [])

            hit_ok += int(score.get("hit_ok") or 0)
            hit_total += int(score.get("hit_total") or 0)
            faith_ok += int(score.get("faith_ok") or 0)
            faith_total += int(score.get("faith_total") or 0)
            pass_runs += int(passed)
            miss_count += run_miss
            unsupported_count += run_unsupported
            annotation_count += run_annotations
            flattened_hit_axis.extend(run_hit_axis)
            flattened_faithfulness_axis.extend(run_faith_axis)
            flattened_tool_outputs.extend(run_tool_outputs)

            experiment_runs.append(
                {
                    "run_index": run_index,
                    "session_id": trace.get("session_id"),
                    "answer": run.get("answer", ""),
                    "tool_outputs": run_tool_outputs,
                    "golden_points": golden_points,
                    "hit_axis": run_hit_axis,
                    "faithfulness_axis": run_faith_axis,
                    "score": {
                        "hit_ok": int(score.get("hit_ok") or 0),
                        "hit_total": int(score.get("hit_total") or 0),
                        "hit_rate": score.get("hit_rate"),
                        "faith_ok": int(score.get("faith_ok") or 0),
                        "faith_total": int(score.get("faith_total") or 0),
                        "faithfulness_rate": score.get("faithfulness_rate"),
                    },
                    "miss_count": run_miss,
                    "unsupported_count": run_unsupported,
                    "annotation_count": run_annotations,
                    "has_issue": not passed,
                    "issue_types": [
                        issue
                        for issue, present in (
                            ("miss", run_miss > 0),
                            ("unsupported", run_unsupported > 0),
                        )
                        if present
                    ],
                    "passed": passed,
                }
            )

        n = int(raw.get("n") or len(raw_runs))
        pass_rate = (
            raw.get("pass_rate")
            if isinstance(raw.get("pass_rate"), (int, float))
            else _rate(pass_runs, len(raw_runs))
        )
        hit_rate = _nullable_rate(hit_ok, hit_total)
        faithfulness_rate = _nullable_rate(faith_ok, faith_total)
        has_hit_issue = miss_count > 0
        has_faith_issue = unsupported_count > 0
        has_issue = pass_rate < 1
        row = {
            "case_id": case_id,
            "bucket": bucket,
            "question": question,
            "answer": experiment_runs[0]["answer"] if len(experiment_runs) == 1 else "",
            "tool_outputs": _ordered_unique(flattened_tool_outputs),
            "golden_points": golden_points,
            "hit_axis": flattened_hit_axis,
            "faithfulness_axis": flattened_faithfulness_axis,
            "score": {
                "hit_ok": hit_ok,
                "hit_total": hit_total,
                "hit_rate": hit_rate,
                "faith_ok": faith_ok,
                "faith_total": faith_total,
                "faithfulness_rate": faithfulness_rate,
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
            "n": n,
            "pass_rate": pass_rate,
            "hit_rate": hit_rate,
            "faithfulness_rate": faithfulness_rate,
            "experiment_runs": experiment_runs,
        }
        rows.append(row)

        for stats in (totals, bucket_stats[bucket]):
            stats["case_count"] += 1
            stats["passed_case_count"] += float(pass_rate)
            stats["issue_case_count"] += int(has_issue)
            stats["hit_issue_case_count"] += int(has_hit_issue)
            stats["faith_issue_case_count"] += int(has_faith_issue)
            stats["hit_ok"] += hit_ok
            stats["hit_total"] += hit_total
            stats["faith_ok"] += faith_ok
            stats["faith_total"] += faith_total

    rows.sort(key=lambda row: (not row["has_issue"], row["case_id"]))

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": {
            "path": str(result_path),
            "exists": result_path.exists(),
            "modified_at": _modified_at(result_path),
        },
        "context": _context(
            root=root,
            manifest=manifest,
            exp_id=exp_id,
            variant=variant,
            source_paths=[result_path, metrics_path],
        ),
        "metrics": _finalize_l2_stats(totals),
        "persisted_metrics": _load_json(metrics_path, {}),
        "breakdowns": {
            "by_bucket": [
                {"bucket": bucket, **_finalize_l2_stats(stats)}
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


FIXTURES_TRACK = "l2_fixtures_judge"
FIXTURES_DATASET_REL = "data/l2_judge_fixtures.json"


def _empty_fixtures_stats() -> dict[str, float]:
    return {
        "case_count": 0,
        "issue_case_count": 0,
        "anchor_count": 0,
        "passed_anchor_count": 0,
        "red_anchor_count": 0,
        "green_anchor_count": 0,
        "red_unsupported_runs": 0,
        "red_runs": 0,
        "green_unsupported_runs": 0,
        "green_runs": 0,
        "not_extracted_runs": 0,
        "anchor_runs": 0,
    }


def _finalize_fixtures_stats(stats: dict[str, float]) -> dict[str, Any]:
    return {
        **{key: _clean_number(value) for key, value in stats.items()},
        "anchor_pass_rate": _nullable_rate(stats["passed_anchor_count"], stats["anchor_count"]),
        # 红锚判 unsupported = 抓到越界；绿锚判 unsupported = 误伤。同一个分子，两种含义。
        "red_anchor_recall": _nullable_rate(stats["red_unsupported_runs"], stats["red_runs"]),
        "green_anchor_fp_rate": _nullable_rate(stats["green_unsupported_runs"], stats["green_runs"]),
        "extract_rate": (1 - stats["not_extracted_runs"] / stats["anchor_runs"])
                        if stats["anchor_runs"] else None,
    }


def _accumulate_fixtures(stats: dict[str, float], case: dict[str, Any], anchors: list[dict[str, Any]]) -> None:
    stats["case_count"] += 1
    stats["issue_case_count"] += int(bool(case.get("has_issue")))
    for anchor in anchors:
        n = int(anchor.get("n") or 0)
        unsupported = int(anchor.get("unsupported_runs") or 0)
        stats["anchor_count"] += 1
        stats["passed_anchor_count"] += int(anchor.get("flag") == "pass")
        stats["anchor_runs"] += n
        stats["not_extracted_runs"] += int(anchor.get("not_extracted_runs") or 0)
        if anchor.get("expect") == "unsupported":
            stats["red_anchor_count"] += 1
            stats["red_runs"] += n
            stats["red_unsupported_runs"] += unsupported
        else:
            stats["green_anchor_count"] += 1
            stats["green_runs"] += n
            stats["green_unsupported_runs"] += unsupported


def _expect_row(expect: str, anchors: list[dict[str, Any]]) -> dict[str, Any]:
    runs = sum(int(a.get("n") or 0) for a in anchors)
    unsupported = sum(int(a.get("unsupported_runs") or 0) for a in anchors)
    not_extracted = sum(int(a.get("not_extracted_runs") or 0) for a in anchors)
    passed = sum(1 for a in anchors if a.get("flag") == "pass")
    return {
        "expect": expect,
        "anchor_count": len(anchors),
        "passed_anchor_count": passed,
        "anchor_pass_rate": _nullable_rate(passed, len(anchors)),
        "anchor_runs": runs,
        "unsupported_runs": unsupported,
        # 红锚读作 recall，绿锚读作假阳率——前端按 expect 决定文案
        "unsupported_run_rate": _nullable_rate(unsupported, runs),
        "not_extracted_runs": not_extracted,
        "extract_rate": (1 - not_extracted / runs) if runs else None,
    }


def build_l2_fixtures_experiment_dashboard_data(
    *,
    root: Path | None = None,
    exp_id: str,
    variant: str,
) -> dict[str, Any]:
    """judge 夹具轨看板：被测对象是 L2 judge 本身，行是 case、列是锚点、最深一层是每次 run 的裁定。"""
    root = root or ROOT
    _, manifest_path, variant_dir = _experiment_paths(root, exp_id, variant)
    manifest = _load_json(manifest_path, {})
    if manifest.get("track") != FIXTURES_TRACK:
        raise ValueError(f"只有 {FIXTURES_TRACK} track 实验支持 judge 夹具 Dashboard")

    result_path = variant_dir / "eval" / "l2_fixtures_case_result.json"
    metrics_path = variant_dir / "eval" / "l2_fixtures_metrics.json"
    raw_results = _load_json(result_path, {})
    if not isinstance(raw_results, dict):
        raw_results = {}

    rows: list[dict[str, Any]] = []
    failed_anchors: list[dict[str, Any]] = []
    all_anchors: list[dict[str, Any]] = []
    totals = _empty_fixtures_stats()
    bucket_stats: dict[str, dict[str, float]] = defaultdict(_empty_fixtures_stats)

    for case_id in sorted(raw_results):
        case = raw_results[case_id]
        if not isinstance(case, dict):
            continue
        anchors = [a for a in case.get("anchors", []) if isinstance(a, dict)]
        if not anchors:
            continue
        bucket = str(case.get("bucket") or "unknown")

        row = {
            **case,
            "case_id": case_id,
            "bucket": bucket,
            "anchors": anchors,
            # 与 L1/L2 轨对齐：落盘叫 runs，出口叫 experiment_runs
            "experiment_runs": case.get("runs", []),
        }
        row.pop("runs", None)
        rows.append(row)

        all_anchors.extend(anchors)
        failed_anchors.extend(
            {**anchor, "bucket": bucket, "question": case.get("question", "")}
            for anchor in anchors
            if anchor.get("flag") != "pass"
        )
        for stats in (totals, bucket_stats[bucket]):
            _accumulate_fixtures(stats, case, anchors)

    rows.sort(key=lambda row: (not row.get("has_issue"), row["case_id"]))

    metrics = _finalize_fixtures_stats(totals)
    metrics["n"] = max((int(row.get("n") or 0) for row in rows), default=0)
    metrics["failed_anchor_count"] = len(failed_anchors)

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": {
            "path": str(result_path),
            "exists": result_path.exists(),
            "modified_at": _modified_at(result_path),
        },
        "context": _context(
            root=root,
            manifest=manifest,
            exp_id=exp_id,
            variant=variant,
            source_paths=[result_path, metrics_path],
            dataset_key="l2_judge_fixtures",
            dataset_rel=FIXTURES_DATASET_REL,
            drift_hint="夹具答案或锚点可能已改，本次结果与历史不可直接比较。",
        ),
        "metrics": metrics,
        "persisted_metrics": _load_json(metrics_path, {}),
        "breakdowns": {
            "by_bucket": [
                {"bucket": bucket, **_finalize_fixtures_stats(stats)}
                for bucket, stats in sorted(bucket_stats.items())
            ],
            "by_expect": [
                _expect_row(expect, [a for a in all_anchors if a.get("expect") == expect])
                for expect in ("unsupported", "supported")
            ],
        },
        "cases": rows,
        "issue_cases": [row for row in rows if row.get("has_issue")],
        "failed_anchors": failed_anchors,
    }
