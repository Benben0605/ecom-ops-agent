
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from src.audit import ToolAudit

def load():
    ROOT = Path(__file__).parents[1]
    eval_cases_path = ROOT / "data" / "eval_cases.json"
    audit_path = ROOT / "logs" / "audit.jsonl"
    run_map_path = ROOT / "logs" / "run_map.json"

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
    is_misfire: bool
    is_hit: bool

def eval_judge() -> dict[str, dict]:
    run_map, cases, audit_lines = load()
    
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

        expected = set(expected_tools)
        actual = set(audit_called)

        # 正样本
        if c["should_call_tool"]:
            is_hit, is_misfire = False, False
            if expected <= actual:   # 期望的全调到
                is_hit = True
            if not actual <= expected: # 调用了期望之外的工具
                is_misfire = True
            
        # 负样本
        else:
            is_hit, is_misfire = None, False
            if len(actual) > 0:
                is_misfire = True

        case_eval_result[case_id] = asdict(
            EvalResult(
                case_id=case_id,
                bucket=bucket,
                called_tools=audit_called,
                spec_tool=expected_tools,
                is_misfire=is_misfire,
                is_hit=is_hit
            )
        )
    print(f"case 覆盖率：{len(case_eval_result) / len(cases) * 100 :.2f}% \n")
    return case_eval_result

if __name__ == "__main__":
    case_eval_result = eval_judge()
    
    case_eval_path = Path(__file__).parents[1] / "logs" / "case_eval_result.json"
    case_eval_path.parent.mkdir(parents=True, exist_ok=True)
    with open(case_eval_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(case_eval_result, ensure_ascii=False, indent=2))
    
    results = case_eval_result.values()
    # cross-case 指标：路由准确率（该调的调对了没）。只有正样本参与计算，负样本不参与计算
    pos_result = [v for v in case_eval_result.values() if v["spec_tool"]]
    hit_rate = len([r for r in pos_result if r["is_hit"]]) / len(pos_result) if pos_result else 0

    # cross-case 指标：误触发率。不期望的工具调用了吗(调了不该调的)，正负样本都要参与计算
    misfire_rate = len([r for r in results if r["is_misfire"]]) / len(results) if results else 0
    
    print(f"路由准确率：{hit_rate * 100:.2f}%")
    print(f"误触发率：{misfire_rate * 100:.2f}%")