from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from src.agent import ChatSession

app = FastAPI()
_sessions: dict[str,ChatSession] = {}

class RequestMessage(BaseModel):
    session_id : str = ""
    user_input: str

class ResponseMessage(BaseModel):
    session_id: str
    assistant_message: str

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

_static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)