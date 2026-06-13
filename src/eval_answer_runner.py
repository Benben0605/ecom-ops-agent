from pathlib import Path
from src.agent import ChatSession
import json
from src.audit import AuditRecorder, MessageRecorder

AUDIT_PATH = Path(__file__).parents[1] / "logs" / "audit.jsonl"
SESSION_MESSAGES_PATH = Path(__file__).parents[1] / "logs" / "session_messages.jsonl"

def eval_answer_run():
    eval_case_path = Path(__file__).parents[1] / "data" / "eval_cases.json"
    eval_cases = json.loads(eval_case_path.read_text(encoding="utf-8"))
    
    run_map_path = Path(__file__).parents[1] / "logs" / "run_map.json"
    
    run_map_list = []
    for case in eval_cases:
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
        MessageRecorder(recorder_path=SESSION_MESSAGES_PATH).record(session.messages)
        
        run_map = {}
        run_map["case_id"] = case["id"]
        run_map["session_id"] = session.id
        run_map_list.append(run_map)

        current_count += 1

    run_map_path.parent.mkdir(parents=True, exist_ok=True)
    with run_map_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(run_map_list, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    eval_answer_run()
    # per_case_run("case_006", 20)