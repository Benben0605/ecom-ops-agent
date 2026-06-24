from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from src.agent import ChatSession
from src.dashboard import build_dashboard_data
from src.l2_annotations import save_l2_annotation
from src.l2_dashboard import build_l2_dashboard_data

app = FastAPI()
_sessions: dict[str,ChatSession] = {}
_static_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"

class RequestMessage(BaseModel):
    session_id : str = ""
    user_input: str

class ResponseMessage(BaseModel):
    session_id: str
    assistant_message: str

class L2RootCauseAnnotationRequest(BaseModel):
    case_id: str
    issue_id: str = ""
    assertion: str
    verdict: str = "unsupported"
    root_cause: str
    root_cause_note: str = ""

def get_or_create(session_id: str) -> ChatSession:
    if session_id in _sessions:
        return _sessions[session_id]
    
    session = ChatSession()
    _sessions[session.id] = session
    return session

@app.post("/chat")
def chat_endpoint(request: RequestMessage) -> ResponseMessage:
    
    session = get_or_create(request.session_id)
    chat_response = session.chat(request.user_input)
    return ResponseMessage(session_id=session.id, assistant_message=chat_response)

@app.get("/api/eval-dashboard")
def eval_dashboard_endpoint() -> dict:
    return build_dashboard_data()


@app.get("/api/l2-eval-dashboard")
def l2_eval_dashboard_endpoint() -> dict:
    return build_l2_dashboard_data()


@app.post("/api/l2-root-cause-annotations")
def save_l2_root_cause_annotation_endpoint(
    request: L2RootCauseAnnotationRequest,
) -> dict:
    try:
        return save_l2_annotation(request.dict())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/dashboard")
@app.get("/l2-dashboard")
@app.get("/l1")
@app.get("/l2")
@app.get("/playground")
def spa_page() -> FileResponse:
    return FileResponse(
        _static_dir / "index.html",
        headers={"Cache-Control": "no-store"},
    )

app.mount(
    "/",
    StaticFiles(directory=_static_dir, html=True, check_dir=False),
    name="static",
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
