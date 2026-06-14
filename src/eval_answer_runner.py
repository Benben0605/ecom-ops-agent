from pathlib import Path
from src.agent import ChatSession
import json
from src.audit import AuditRecorder, MessageRecorder
from src.agent import SupervisorAgent

AUDIT_PATH = Path(__file__).parents[1] / "logs" / "audit.jsonl"
SESSION_MESSAGES_PATH = Path(__file__).parents[1] / "logs" / "session_messages.jsonl"

def _default_make_agent(recorder):
    return ChatSession(audit_recorder=recorder)

def eval_answer_run(make_agent=_default_make_agent):
    """跑全套评估。make_agent(recorder)->agent 决定打哪套 agent（单/多 Agent 对比用）。
    agent 须满足 ChatSession 同接口：.chat(str)->str / .id / .messages / 注入 recorder。"""
    eval_case_path = Path(__file__).parents[1] / "data" / "eval_cases.json"
    eval_cases = json.loads(eval_case_path.read_text(encoding="utf-8"))

    run_map_path = Path(__file__).parents[1] / "logs" / "run_map.json"

    run_map_list = []
    for case in eval_cases:
        session = make_agent(AuditRecorder(recorder_path=AUDIT_PATH))
        session.chat(case["question"])
        MessageRecorder(recorder_path=SESSION_MESSAGES_PATH).record(
            {
                "session_id": session.id,
                "messages": session.messages
            }
        )
        
        run_map = {}
        run_map["case_id"] = case["id"]
        run_map["session_id"] = session.id
        run_map_list.append(run_map)
    run_map_path.parent.mkdir(parents=True, exist_ok=True)
    with run_map_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(run_map_list, ensure_ascii=False, indent=2))

def per_case_run(case_id: str, run_count: int):
    eval_case_path = Path(__file__).parents[1] / "data" / "eval_cases.json"
    eval_cases = json.loads(eval_case_path.read_text(encoding="utf-8"))
    
    run_map_path = Path(__file__).parents[1] / "logs" / "run_map.json"
    
    run_map_list, current_count = [], 1
    case = next((c for c in eval_cases if c["id"] == case_id), None)
    while case is not None and current_count <= run_count:
        session = ChatSession(audit_recorder=AuditRecorder(recorder_path=AUDIT_PATH))
        session.chat(case["question"])
        MessageRecorder(recorder_path=SESSION_MESSAGES_PATH).record(
            {
                "session_id": session.id,
                "messages": session.messages
            }
        )
        
        run_map = {}
        run_map["case_id"] = case["id"]
        run_map["session_id"] = session.id
        run_map_list.append(run_map)

        current_count += 1

    run_map_path.parent.mkdir(parents=True, exist_ok=True)
    with run_map_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(run_map_list, ensure_ascii=False, indent=2))

def multi_agent_per_case(case_id: str, run_count: int):
    eval_case_path = Path(__file__).parents[1] / "data" / "eval_cases.json"
    eval_cases = json.loads(eval_case_path.read_text(encoding="utf-8"))
    
    run_map_path = Path(__file__).parents[1] / "logs" / "run_map.json"
    
    run_map_list, current_count = [], 1
    case = next((c for c in eval_cases if c["id"] == case_id), None)
    while case is not None and current_count <= run_count:
        supervisor_agent = SupervisorAgent(
            audit_recorder=AuditRecorder(recorder_path=AUDIT_PATH),
            message_recorder=MessageRecorder(recorder_path=SESSION_MESSAGES_PATH)
        )
        supervisor_agent.chat(case["question"])
        
        run_map = {}
        run_map["case_id"] = case["id"]
        run_map["session_id"] = supervisor_agent.id
        run_map_list.append(run_map)

        current_count += 1

    run_map_path.parent.mkdir(parents=True, exist_ok=True)
    with run_map_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(run_map_list, ensure_ascii=False, indent=2))

def multi_agent_run():
    eval_case_path = Path(__file__).parents[1] / "data" / "eval_cases.json"
    eval_cases = json.loads(eval_case_path.read_text(encoding="utf-8"))
    
    run_map_path = Path(__file__).parents[1] / "logs" / "run_map.json"
    
    run_map_list, current_count = [], 1
    for case in eval_cases:
        supervisor_agent = SupervisorAgent(
            audit_recorder=AuditRecorder(recorder_path=AUDIT_PATH),
            message_recorder=MessageRecorder(recorder_path=SESSION_MESSAGES_PATH)
        )
        supervisor_agent.chat(case["question"])
        
        run_map = {}
        run_map["case_id"] = case["id"]
        run_map["session_id"] = supervisor_agent.id
        run_map_list.append(run_map)

        current_count += 1

    run_map_path.parent.mkdir(parents=True, exist_ok=True)
    with run_map_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(run_map_list, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    # 跑所有评估集case(单Agent)
    #  eval_answer_run()
    
    # 跑多次per-case（单Agent）
    #  per_case_run("case_006", 20)
    
    # 跑多次per-case（多Agent）
    # multi_agent_per_case("case_017", 1)

    # 跑所有评估集case（多Agent）
    multi_agent_run()