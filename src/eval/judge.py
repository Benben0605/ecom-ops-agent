
from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from src.audit import ToolAudit

def load(run_dir: Path | None = None):
    ROOT = Path(__file__).parents[2]
    run_dir = run_dir or ROOT / "logs"
    eval_cases_path = ROOT / "data" / "eval_cases.json"
    audit_path = run_dir / "audit.jsonl"
    run_map_path = run_dir / "run_map.json"

    run_map = json.loads(run_map_path.read_text(encoding="utf-8"))
    cases = json.loads(eval_cases_path.read_text(encoding="utf-8"))
    audit_lines : list[ToolAudit] = []
    with open(audit_path, "r", encoding="utf-8") as f:
        for line in f:
            audit_lines.append(ToolAudit(**json.loads(line)))
    
    return run_map, cases, audit_lines

@dataclass
class EvalResult:
    case_id: str
    bucket: str
    called_tools: list
    spec_tool: list[str] | None
    missing_tools: list[str]
    unexpected_tools: list[str]
    is_misfire: bool
    is_hit: bool | None

def _counter_diff(left: Counter, right: Counter) -> list[str]:
    diff: list[str] = []
    for tool_name, count in (left - right).items():
        diff.extend([tool_name] * count)
    return diff

def summarize_results(case_eval_result: dict[str, dict]) -> dict:
    results = list(case_eval_result.values())
    pos_result = [v for v in results if v["spec_tool"]]
    route_hit_count = len([r for r in pos_result if r["is_hit"]])
    route_error_count = len([r for r in pos_result if r["is_hit"] is False])
    misfire_count = len([r for r in results if r["is_misfire"]])

    return {
        "evaluated_case_count": len(results),
        "positive_case_count": len(pos_result),
        "route_hit_count": route_hit_count,
        "route_error_count": route_error_count,
        "routing_accuracy": route_hit_count / len(pos_result) if pos_result else 0,
        "misfire_count": misfire_count,
        "misfire_rate": misfire_count / len(results) if results else 0,
    }

def eval_judge(run_dir: Path | None = None) -> dict[str, dict]:
    run_map, cases, audit_lines = load(run_dir)
    
    # 1）按 case_id 归集这个 case 实际调用的工具
    #   只认 run_map 中的 session_id。 case_id -> session_id -> 累加 tool_name 
    called : dict[list] = {}
    for r in run_map:
        case_id = r["case_id"]
        session_id = r["session_id"]
        audit_called = [a.tool_name for a in audit_lines if a.session_id == session_id and a.tool_name is not None]
        called[case_id] = audit_called

    case_eval_result: dict[str, EvalResult] = {}
    
    for c in cases:
        case_id = c["id"]
        bucket = c["bucket"]
        if case_id not in called:
            continue
        assert c["should_call_tool"] == bool(c["expected_calls"])
        audit_called = called[case_id]
        expected_tools = [d["tool_name"] for d in c["expected_calls"] if d["tool_name"] is not None]

        expected = Counter(expected_tools)
        actual = Counter(audit_called)
        missing_tools = _counter_diff(expected, actual)
        unexpected_tools = _counter_diff(actual, expected)

        # 正样本
        if c["should_call_tool"]:
            is_hit, is_misfire = False, False
            if not missing_tools:   # 期望的全调到，重复调用也要满足次数
                is_hit = True
            if unexpected_tools: # 调用了期望之外的工具，或同一工具多调
                is_misfire = True
            
        # 负样本
        else:
            is_hit, is_misfire = None, False
            if sum(actual.values()) > 0:
                is_misfire = True

        case_eval_result[case_id] = asdict(
            EvalResult(
                case_id=case_id,
                bucket=bucket,
                called_tools=audit_called,
                spec_tool=expected_tools,
                missing_tools=missing_tools,
                unexpected_tools=unexpected_tools,
                is_misfire=is_misfire,
                is_hit=is_hit
            )
        )
    print(f"case 覆盖率：{len(case_eval_result) / len(cases) * 100 :.2f}% \n")
    return case_eval_result

if __name__ == "__main__":
    case_eval_result = eval_judge()
    
    case_eval_path = Path(__file__).parents[2] / "logs" / "case_eval_result.json"
    case_eval_path.parent.mkdir(parents=True, exist_ok=True)
    with open(case_eval_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(case_eval_result, ensure_ascii=False, indent=2))
    
    metrics = summarize_results(case_eval_result)
    metrics_path = Path(__file__).parents[2] / "logs" / "eval_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(metrics, ensure_ascii=False, indent=2))
    
    print(f"路由准确率：{metrics['routing_accuracy'] * 100:.2f}%")
    print(f"误触发率：{metrics['misfire_rate'] * 100:.2f}%")
