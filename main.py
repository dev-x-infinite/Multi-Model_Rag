"""
main.py
FastAPI wrapper: simple login (username/password, no token) +
per-user isolated ingestion and search.
"""

import shutil
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ingestion import MultiModalIngestion
from vector_store import VectorStoreManager
from agent import ask
import auth

app = FastAPI(title="Multi-Modal RAG Assistant")

ingestion = MultiModalIngestion()
store = VectorStoreManager()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


class AuthRequest(BaseModel):
    username: str
    password: str


class QueryResponse(BaseModel):
    answer: str


@app.post("/register")
async def register(request: AuthRequest):
    try:
        auth.create_user(request.username, request.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "registered", "username": request.username}


@app.post("/login")
async def login(request: AuthRequest):
    if not auth.authenticate_user(request.username, request.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    # No token -- the frontend just remembers the username and sends it
    # along with every future request as user_id.
    return {"status": "logged in", "username": request.username}


@app.post("/upload")
async def upload_file(user_id: str = Form(...), file: UploadFile = File(...)):
    # Per-user folder so two users uploading "resume.pdf" don't overwrite
    # each other's file on disk (Chroma isolation is separate, handled
    # by vector_store's user_id filtering -- this is just the raw file).
    user_dir = UPLOAD_DIR / user_id
    user_dir.mkdir(exist_ok=True)
    file_path = user_dir / file.filename

    if store.source_exists(file.filename, user_id):
        return {
            "filename": file.filename,
            "status": "already ingested, skipped",
            "total_chunks": store.count(user_id),
        }

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        chunks = ingestion.ingest_file(str(file_path))
        added = store.add_chunks(chunks, user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "filename": file.filename,
        "chunks_created": added,
        "total_chunks": store.count(user_id),
    }


@app.post("/query", response_model=QueryResponse)
async def query(user_id: str = Form(...), question: str = Form(...)):
    try:
        answer = ask(question, user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return QueryResponse(answer=answer)


@app.get("/health")
async def health(user_id: str | None = None):
    if user_id:
        return {"status": "ok", "chunks_stored": store.count(user_id)}
    return {"status": "ok", "chunks_stored": store.count()}


# Mounted LAST so it doesn't shadow the routes above
app.mount("/", StaticFiles(directory="static", html=True), name="static")