import json
import requests
from typing import List, Dict, Any, Generator

SYSTEM_PROMPT = """당신은 대한민국 종합 법률(민법, 형법, 주택·상가임대차보호법, 근로기준법, 도로교통법, 전자상거래법 등) 전문 법률 AI 상담 비서입니다.
당신의 임무는 아래 제공된 [참고 법률 및 판례/행정해석]만을 철저히 근거로 삼아, 사용자의 질문에 정확하고 명쾌하게 답변하는 것입니다.

[답변 작성 원칙]
1. [환각 방지]: 반드시 제공된 [참고 법률 및 판례/행정해석]의 내용에 기반해서만 답변하십시오. 제공된 자료에 근거가 없는 내용은 절대로 추측하거나 지어내지 마십시오.
2. [출처 필수 명시]: 답변의 핵심 문장마다 근거가 되는 법령명과 조항 번호(예: 「주택임대차보호법」 제3조의3, 「형법」 제347조, 「근로기준법」 제55조)를 명확히 인용하십시오.
3. [구조화된 설명]: 
   - 1) 핵심 결론 (한눈에 알아볼 수 있는 명확한 요약)
   - 2) 법적 근거 및 상세 설명 (적용 조건, 대항력/구제 절차, 손해배상 등)
   - 3) 유의사항 및 실무 팁 (입증 책임, 시효 기간, 고소/신청 기한 등)
4. [불확실성 안내]: 제공된 법령 자료로 명확히 판단하기 어렵거나 사실관계에 따라 해석이 달라질 수 있는 경우, 변호사, 법무사, 공인노무사 또는 대한법률구조공단(국번없이 132) 상담을 안내하십시오.
"""

USER_PROMPT_TEMPLATE = """[참고 법률 및 판례/행정해석]
{context}

[사용자 질문]
{question}

위 [참고 법률 및 판례/행정해석]을 바탕으로 질문에 대해 명확한 근거와 함께 답변해 주세요."""


class OllamaLegalGenerator:
    def __init__(self, model_name: str = "qwen2.5:3b", base_url: str = "http://127.0.0.1:11434"):
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")

    def format_context(self, retrieved_docs: List[Dict[str, Any]], graph_triples: List[Dict[str, Any]] = None) -> str:
        """검색된 조문 문서와 지식 그래프 트리플을 LLM 프롬프트용 통합 컨텍스트로 구성"""
        context_blocks = []

        # 1. 지식 그래프 트리플(인과관계 경로) 우선 배치
        if graph_triples:
            graph_lines = ["【법률 지식 그래프(Knowledge Graph) 인과관계 연결망】"]
            for t in graph_triples:
                law_str = f" (법적근거: {t['law']})" if t.get("law") else ""
                graph_lines.append(f"• [{t['subject']}] ──({t['predicate']})──> [{t['object']}]{law_str}")
            context_blocks.append("\n".join(graph_lines))

        # 2. 검색된 조문 원문 배치
        if retrieved_docs:
            doc_lines = ["【관련 법률 조문 및 판례 원문】"]
            for i, doc in enumerate(retrieved_docs, start=1):
                source = doc.get("source", "출처 미상")
                title = doc.get("title", "")
                content = doc.get("content", "")
                cat = doc.get("category", "")
                doc_lines.append(f"[{i}] [{cat}] {source} ({title})\n{content}")
            context_blocks.append("\n\n".join(doc_lines))

        if not context_blocks:
            return "관련된 법률 또는 판례 자료가 검색되지 않았습니다."

        return "\n\n" + ("=" * 40) + "\n\n".join(context_blocks)

    def generate_response(self, question: str, retrieved_docs: List[Dict[str, Any]]) -> str:
        """Ollama API를 호출하여 단일 응답 생성 (Non-streaming)"""
        context_str = self.format_context(retrieved_docs)
        user_prompt = USER_PROMPT_TEMPLATE.format(context=context_str, question=question)

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,  # 법률 도메인 특성상 환각 최소화를 위해 낮은 온도 유지
                "top_p": 0.9
            }
        }

        try:
            res = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=60)
            res.raise_for_status()
            data = res.json()
            return data["message"]["content"]
        except requests.exceptions.RequestException as e:
            return f"[오류] Ollama 서버 연결에 실패했습니다: {e}\n(Ollama가 실행 중인지와 `{self.model_name}` 모델이 설치되어 있는지 확인해주세요.)"

    def stream_response(self, question: str, retrieved_docs: List[Dict[str, Any]]) -> Generator[str, None, None]:
        """스트리밍 응답 생성 (Streamlit 및 터미널 실시간 출력용)"""
        context_str = self.format_context(retrieved_docs)
        user_prompt = USER_PROMPT_TEMPLATE.format(context=context_str, question=question)

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "stream": True,
            "keep_alive": "30m",  # 메모리에 모델 상주 유지 (콜드 스타트 방지)
            "options": {
                "temperature": 0.1,
                "top_p": 0.9
            }
        }

        try:
            with requests.post(f"{self.base_url}/api/chat", json=payload, stream=True, timeout=(10.0, 180.0)) as res:
                res.raise_for_status()
                for line in res.iter_lines():
                    if line:
                        chunk_json = json.loads(line.decode("utf-8"))
                        if "message" in chunk_json and "content" in chunk_json["message"]:
                            yield chunk_json["message"]["content"]
        except requests.exceptions.RequestException as e:
            yield f"\n[오류] Ollama 연결 실패: {e}\n(터미널에서 `ollama run {self.model_name}` 실행 여부를 확인하세요.)"


if __name__ == "__main__":
    generator = OllamaLegalGenerator()
    dummy_docs = [
        {
            "doc_type": "법령",
            "source": "근로기준법 제55조",
            "title": "휴일",
            "content": "사용자는 근로자에게 1주에 평균 1회 이상의 유급휴일을 보장하여야 한다."
        }
    ]
    print("Testing prompt generation...")
    print(generator.format_context(dummy_docs))
