from typing import Dict, Any, Generator, Tuple, List
from src.parser import load_legal_corpus, get_all_categories
from src.retriever import HierarchicalLegalRetriever
from src.graph_engine import LegalKnowledgeGraph
from src.generator import OllamaLegalGenerator

class KoreanAllLawsGraphRAGPipeline:
    """
    대한민국 전 분야 종합 법률 Hybrid GraphRAG 파이프라인
    - 1단계: Hierarchical Retriever (Category Routing + BM25 + Persistent ChromaDB)
    - 2단계: Legal Knowledge Graph (Subject-Predicate-Object 트리플 인과관계 탐색)
    - 3단계: Ollama LLM Generator (qwen2.5:3b)
    """
    def __init__(self, model_name: str = "qwen2.5:3b", ollama_base_url: str = "http://127.0.0.1:11434"):
        print("[1/3] 전체 법률/판례 코퍼스 로드 및 계층적 인덱싱...")
        self.corpus = load_legal_corpus()
        self.retriever = HierarchicalLegalRetriever(documents=self.corpus)
        self.categories = get_all_categories(self.corpus)
        print(f"-> 총 {len(self.corpus)}건 조문 로드, {len(self.categories)}개 분야 인덱싱 완료")

        print("[2/3] 법률 지식 그래프(Knowledge Graph) 엔진 로드...")
        self.kg = LegalKnowledgeGraph()

        print(f"[3/3] Ollama 종합 법률 생성기 초기화 ({model_name})...")
        self.generator = OllamaLegalGenerator(model_name=model_name, base_url=ollama_base_url)

    def ask(self, question: str, category: str = "auto", top_k: int = 3, bm25_weight: float = 0.6) -> Dict[str, Any]:
        """질문에 대해 텍스트 검색 + 지식 그래프 다단계 탐색 후 답변 생성"""
        # 1. 조문 텍스트 검색 및 분야 자동 판정
        retrieved_docs, resolved_category = self.retriever.hybrid_search(
            query=question,
            category=category,
            top_k=top_k,
            bm25_weight=bm25_weight
        )

        # 2. 판정된 분야(resolved_category) 기반 고정밀 지식 그래프 트리플 탐색
        graph_triples = self.kg.find_relevant_triples(
            query=question,
            category=resolved_category,
            top_k=3,
            min_score=2.0
        )

        # 3. 답변 생성
        context_str = self.generator.format_context(retrieved_docs, graph_triples)
        answer = self.generator.generate_response(question, retrieved_docs)
        
        return {
            "question": question,
            "category": resolved_category,
            "answer": answer,
            "retrieved_docs": retrieved_docs,
            "graph_triples": graph_triples
        }

    def ask_stream(self, question: str, category: str = "auto", top_k: int = 3, bm25_weight: float = 0.6):
        """스트리밍 방식으로 검색된 문서, 그래프 트리플 및 토큰 반환"""
        # 1. 텍스트 검색 및 분야 판정
        retrieved_docs, resolved_category = self.retriever.hybrid_search(
            query=question,
            category=category,
            top_k=top_k,
            bm25_weight=bm25_weight
        )

        # 2. 판정된 분야 기반 고정밀 지식 그래프 트리플 탐색
        graph_triples = self.kg.find_relevant_triples(
            query=question,
            category=resolved_category,
            top_k=3,
            min_score=2.0
        )

        # 3. 스트리밍 생성 준비
        context_str = self.generator.format_context(retrieved_docs, graph_triples)
        stream_gen = self.generator.stream_response(question, retrieved_docs)
        
        return retrieved_docs, graph_triples, resolved_category, stream_gen


if __name__ == "__main__":
    pipeline = KoreanAllLawsGraphRAGPipeline()
    test_q = "알바생 12시간 일하는데 주휴수당 안 주면 처벌받나요?"
    print(f"\n[질문: {test_q}]")
    docs, triples, cat, _ = pipeline.ask_stream(test_q)
    print(f"분야: {cat}")
    print("지식 그래프 경로:", len(triples), "개 발견")
    for t in triples:
        print(f" - [{t['subject']}] -({t['predicate']})-> [{t['object']}]")
