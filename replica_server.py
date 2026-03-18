import argparse
import time
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

app = FastAPI()
REPLICA_ID = 1
OLLAMA_URL = "http://localhost:11434"
MODEL_NAME = "llama3.2:3b"

class InferenceRequest(BaseModel):
    prompt: str
    max_tokens: int = 100

class InferenceResponse(BaseModel):
    replica_id: int
    response: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int

@app.get("/health")
def health():
    return {"status": "ok", "replica_id": REPLICA_ID}

@app.post("/infer", response_model=InferenceResponse)
def infer(req: InferenceRequest):
    start = time.time()
    try:
        result = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": req.prompt,
                "stream": False,
                "options": {"num_predict": req.max_tokens}
            },
            timeout=60.0
        )
        result.raise_for_status()
        data = result.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama error: {str(e)}")

    latency_ms = (time.time() - start) * 1000
    return InferenceResponse(
        replica_id=REPLICA_ID,
        response=data.get("response", ""),
        latency_ms=latency_ms,
        prompt_tokens=data.get("prompt_eval_count", 0),
        completion_tokens=data.get("eval_count", 0)
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--replica-id", type=int, default=1)
    parser.add_argument("--model", type=str, default="llama3.2:3b")
    args = parser.parse_args()

    REPLICA_ID = args.replica_id
    MODEL_NAME = args.model

    uvicorn.run(app, host="0.0.0.0", port=args.port)
