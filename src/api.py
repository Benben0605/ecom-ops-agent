from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from src.agent import ChatSession
from src.dashboard.main import build_dashboard_data
from src.dashboard.experiment_adapter import build_l2_fixtures_experiment_dashboard_data
from src.experiment.runner import list_experiments
from src.experiment.compare import compare_with_detail
from src.eval.l2.annotations import save_l2_annotation
from src.eval.l2.dashboard import build_l2_dashboard_data

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
    exp_id: str | None = None
    variant: str | None = None
    run_index: int | None = None

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
def eval_dashboard_endpoint(
    exp_id: str | None = None,
    variant: str | None = None,
) -> dict:
    try:
        return build_dashboard_data(exp_id=exp_id, variant=variant)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/l2-eval-dashboard")
def l2_eval_dashboard_endpoint(
    exp_id: str | None = None,
    variant: str | None = None,
) -> dict:
    try:
        return build_l2_dashboard_data(exp_id=exp_id, variant=variant)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/l2-fixtures-dashboard")
def l2_fixtures_dashboard_endpoint(exp_id: str, variant: str) -> dict:
    # 本轨没有 legacy 源：夹具结果只存在于某次实验里，exp_id/variant 必填
    try:
        return build_l2_fixtures_experiment_dashboard_data(exp_id=exp_id, variant=variant)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/experiments")
def experiments_endpoint() -> list:
    return list_experiments()


@app.get("/api/experiments/{exp_id}/compare")
def experiment_compare_endpoint(
    exp_id: str, a: str | None = None, b: str | None = None
) -> dict:
    manifests = {m["exp_id"]: m for m in list_experiments()}
    manifest = manifests.get(exp_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"实验不存在：{exp_id}")
    names = [v["name"] for v in manifest["variants"]]
    if len(names) < 2:
        raise HTTPException(status_code=400, detail="该实验变体不足 2 个，无法对比")
    variant_a = a or names[0]
    variant_b = b or names[1]
    return compare_with_detail(exp_id, variant_a, variant_b)


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
@app.get("/ab")
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
