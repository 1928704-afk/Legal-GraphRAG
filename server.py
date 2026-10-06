import json
import asyncio
from typing import Optional
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx
import os
import sys

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.pipeline import KoreanAllLawsGraphRAGPipeline
from src.generator import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

app = FastAPI(title="Korean All-Laws GraphRAG")

# 전역 GraphRAG 파이프라인 싱글톤
rag_pipeline: Optional[KoreanAllLawsGraphRAGPipeline] = None

def get_rag():
    global rag_pipeline
    if rag_pipeline is None:
        rag_pipeline = KoreanAllLawsGraphRAGPipeline(model_name="qwen2.5:3b")
    return rag_pipeline


class ChatRequest(BaseModel):
    question: str
    category: str = "auto"
    top_k: int = 3
    bm25_weight: float = 0.6
    model_name: str = "qwen2.5:3b"


@app.on_event("startup")
async def startup_event():
    rag = get_rag()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                "http://127.0.0.1:11434/api/generate",
                json={"model": "qwen2.5:3b", "prompt": "", "keep_alive": "30m"}
            )
            print("[웜업 완료] Qwen 2.5 3B 모델 상주 준비 완료.")
    except Exception as e:
        print(f"[웜업 알림]: {e}")


@app.get("/api/categories")
def get_categories():
    rag = get_rag()
    return {"categories": ["auto", "전체"] + rag.categories}


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    rag = get_rag()
    
    # 1. 텍스트 검색 + 지식 그래프 트리플 탐색
    retrieved_docs, graph_triples, resolved_cat, _ = rag.ask_stream(
        question=req.question,
        category=req.category,
        top_k=req.top_k,
        bm25_weight=req.bm25_weight
    )

    # 2. 통합 컨텍스트 구성 (지식 그래프 + 조문 원문)
    context_str = rag.generator.format_context(retrieved_docs, graph_triples)
    user_prompt = USER_PROMPT_TEMPLATE.format(context=context_str, question=req.question)

    payload = {
        "model": req.model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "stream": True,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.1,
            "top_p": 0.9
        }
    }

    async def event_generator():
        # 메타데이터 전송 (검색된 조문 + 지식 그래프 인과관계 경로)
        meta_payload = {
            "category": resolved_cat,
            "docs": retrieved_docs,
            "triples": graph_triples
        }
        yield f"event: meta\ndata: {json.dumps(meta_payload, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.005)

        # 비동기 토큰 스트리밍
        try:
            timeout_cfg = httpx.Timeout(180.0, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout_cfg) as client:
                async with client.stream("POST", "http://127.0.0.1:11434/api/chat", json=payload) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_lines():
                        if chunk:
                            try:
                                chunk_json = json.loads(chunk)
                                if "message" in chunk_json and "content" in chunk_json["message"]:
                                    text_piece = chunk_json["message"]["content"]
                                    data_str = json.dumps({"text": text_piece}, ensure_ascii=False)
                                    yield f"event: message\ndata: {data_str}\n\n"
                            except json.JSONDecodeError:
                                pass
        except Exception as e:
            err_data = json.dumps({"text": f"\n\n[오류 발생]: {e}"}, ensure_ascii=False)
            yield f"event: message\ndata: {err_data}\n\n"

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/health")
def health():
    rag = get_rag()
    return {
        "status": "ok",
        "total_laws_indexed": len(rag.corpus),
        "total_kg_triples": rag.kg.graph.number_of_edges(),
        "categories": rag.categories
    }


# 정적 파일 서빙
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)

@app.get("/", response_class=HTMLResponse)
def index():
    html_path = os.path.join(static_dir, "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()

app.mount("/static", StaticFiles(directory=static_dir), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8501, reload=False)
