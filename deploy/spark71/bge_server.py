"""bge embedding 服务（spark-71，CPU，OpenAI 兼容 /v1/embeddings）。

部署：scp 到 ~/reproforge_serve/bge_server.py，uvicorn 起 :8002。
依赖：sentence-transformers, fastapi, uvicorn（spark-71 comfyui-env 已有 torch）。
"""
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

MODEL_PATH = "/home/Developer/models/bge-large-zh-v1.5"

app = FastAPI(title="ReproForge bge embedding")
_model = SentenceTransformer(MODEL_PATH, device="cpu")


class EmbReq(BaseModel):
    input: list[str]
    model: str = "bge-large-zh"


@app.post("/v1/embeddings")
def embeddings(req: EmbReq):
    vecs = _model.encode(req.input, normalize_embeddings=True).tolist()
    return {"data": [{"embedding": v} for v in vecs], "model": req.model}


@app.get("/v1/models")
def models():
    return {"data": [{"id": "bge-large-zh"}]}
