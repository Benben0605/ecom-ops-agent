from pathlib import Path
from src.agent import ChatSession
import json
from datetime import datetime
from src.audit import AuditRecorder, MessageRecorder
from src.agent import SupervisorAgent

LOGS_ROOT = Path(__file__).parents[2] / "logs"

def _run_dir() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = LOGS_ROOT / "runs" / ts
    d.mkdir(parents=True, exist_ok=True)
    return d

def _case_user_context(case: dict) -> dict | None:
    """case 的 role（会话属性）/ user_id（画像库主键）两字段正交、各自可选；都缺 = 游客零注入"""
    if "role" in case or "user_id" in case:
        return {"role": case.get("role"), "user_id": case.get("user_id")}
    return None

def _default_make_agent(recorder, user_context=None):
    return ChatSession(audit_recorder=recorder, user_context=user_context)

def eval_answer_run(make_agent=_default_make_agent, run_dir: Path | None = None,
                    case_filter: list[str] | None = None) -> Path:
    """跑全套评估。make_agent(recorder, user_context)->agent 决定打哪套 agent（单/多 Agent 对比用）。
    user_context 由 case 的 role/user_id 字段组装（都缺席=游客=None，零注入）。
    agent 须满足 ChatSession 同接口：.chat(str)->str / .id / .messages / 注入 recorder。
    run_dir 指定 trace 落盘目录（实验 harness 传隔离目录）；不传则自动建 logs/runs/<ts>/。
    case_filter 给一组 case_id 时只跑子集（冒烟验证省 API 预算）。
    返回实际落盘目录，供 judge 对齐读取。"""
    eval_case_path = Path(__file__).parents[2] / "data" / "eval_cases.json"
    eval_cases = json.loads(eval_case_path.read_text(encoding="utf-8"))
    if case_filter is not None:
        keep = set(case_filter)
        eval_cases = [c for c in eval_cases if c["id"] in keep]

    run = run_dir or _run_dir()
    run.mkdir(parents=True, exist_ok=True)

    run_map_list = []
    for case in eval_cases:
        session = make_agent(AuditRecorder(recorder_path=run / "audit.jsonl"), _case_user_context(case))
        session.chat(case["question"])
        MessageRecorder(recorder_path=run / "session_messages.jsonl").record(
            {
                "session_id": session.id,
                "messages": session.messages
            }
        )
        run_map_list.append({"case_id": case["id"], "session_id": session.id})

    with (run / "run_map.json").open("w", encoding="utf-8") as f:
        f.write(json.dumps(run_map_list, ensure_ascii=False, indent=2))
    return run

def per_case_run(case_id: str, run_count: int):
    eval_case_path = Path(__file__).parents[2] / "data" / "eval_cases.json"
    eval_cases = json.loads(eval_case_path.read_text(encoding="utf-8"))

    run = _run_dir()

    run_map_list, current_count = [], 1
    case = next((c for c in eval_cases if c["id"] == case_id), None)
    while case is not None and current_count <= run_count:
        session = ChatSession(audit_recorder=AuditRecorder(recorder_path=run / "audit.jsonl"),
                              user_context=_case_user_context(case))
        session.chat(case["question"])
        MessageRecorder(recorder_path=run / "session_messages.jsonl").record(
            {
                "session_id": session.id,
                "messages": session.messages
            }
        )
        run_map_list.append({"case_id": case["id"], "session_id": session.id})
        current_count += 1

    with (run / "run_map.json").open("w", encoding="utf-8") as f:
        f.write(json.dumps(run_map_list, ensure_ascii=False, indent=2))

def multi_agent_per_case(case_id: str, run_count: int):
    eval_case_path = Path(__file__).parents[2] / "data" / "eval_cases.json"
    eval_cases = json.loads(eval_case_path.read_text(encoding="utf-8"))

    run = _run_dir()

    run_map_list, current_count = [], 1
    case = next((c for c in eval_cases if c["id"] == case_id), None)
    while case is not None and current_count <= run_count:
        supervisor_agent = SupervisorAgent(
            audit_recorder=AuditRecorder(recorder_path=run / "audit.jsonl"),
            message_recorder=MessageRecorder(recorder_path=run / "session_messages.jsonl")
        )
        supervisor_agent.chat(case["question"])
        run_map_list.append({"case_id": case["id"], "session_id": supervisor_agent.id})
        current_count += 1

    with (run / "run_map.json").open("w", encoding="utf-8") as f:
        f.write(json.dumps(run_map_list, ensure_ascii=False, indent=2))

def multi_agent_run(run_dir: Path | None = None) -> Path:
    eval_case_path = Path(__file__).parents[2] / "data" / "eval_cases.json"
    eval_cases = json.loads(eval_case_path.read_text(encoding="utf-8"))

    run = run_dir or _run_dir()
    run.mkdir(parents=True, exist_ok=True)

    run_map_list = []
    for case in eval_cases:
        supervisor_agent = SupervisorAgent(
            audit_recorder=AuditRecorder(recorder_path=run / "audit.jsonl"),
            message_recorder=MessageRecorder(recorder_path=run / "session_messages.jsonl")
        )
        supervisor_agent.chat(case["question"])
        run_map_list.append({"case_id": case["id"], "session_id": supervisor_agent.id})

    with (run / "run_map.json").open("w", encoding="utf-8") as f:
        f.write(json.dumps(run_map_list, ensure_ascii=False, indent=2))
    return run

if __name__ == "__main__":
    # 跑所有评估集case(单Agent)
    # eval_answer_run()

    # 跑多次per-case（单Agent）
    per_case_run("case_067", 5)

    # 跑多次per-case（多Agent）
    # multi_agent_per_case("case_041", 2)

    # 跑所有评估集case（多Agent）
    # multi_agent_run()
