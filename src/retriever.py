import os
import re
from typing import List, Dict, Any, Tuple, Optional
from rank_bm25 import BM25Okapi
from src.parser import LaborLawDocument, load_legal_corpus

CHROMA_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "chroma_db")

def simple_korean_tokenizer(text: str) -> List[str]:
    """한국어 법률 텍스트용 경량 토크나이저"""
    tokens = re.findall(r'[가-힣a-zA-Z0-9_]+', text.lower())
    bigrams = []
    for token in tokens:
        if len(token) >= 2:
            for i in range(len(token) - 1):
                bigrams.append(token[i:i+2])
    return tokens + bigrams


CATEGORY_KEYWORDS = {
    "부동산/임대차": ["전세", "월세", "보증금", "임대차", "임대인", "임차인", "세입자", "집주인", "계약갱신", "권리금", "상가", "묵시적", "확정일자", "대항력", "우선변제", "임차권등기"],
    "노동/근로": ["주휴수당", "알바", "퇴직금", "해고", "근로계약", "근로자", "사용자", "통상임금", "평균임금", "연차", "수습", "5인미만", "연장근로", "야간근로", "휴게"],
    "형사/범죄": ["사기", "고소", "형법", "폭행", "모욕", "명예훼손", "횡령", "배임", "징역", "벌금", "친고죄", "반의사불벌죄", "기망"],
    "교통/사고": ["음주운전", "교통사고", "12대중과실", "뺑소니", "혈중알코올농도", "신호위반", "중앙선", "면허", "운전"],
    "소비자/금융/IT": ["환불", "청약철회", "전자상거래", "최고이자율", "이자제한법", "개인정보", "동의", "쇼핑몰"],
    "민사/계약": ["소멸시효", "채무불이행", "손해배상", "불법행위", "계약금", "해약금", "채권", "이행", "빌려", "대여금", "차용", "차용증", "돈"]
}


class HierarchicalLegalRetriever:
    """
    대규모 대한민국 법령을 위한 2단계 계층적 하이브리드 검색기
    1단계: 법률 분야 라우팅 (Metadata Category Filter / Auto Detector)
    2단계: BM25 + Persistent ChromaDB Dense Search (RRF Re-ranking)
    """
    def __init__(self, documents: List[LaborLawDocument] = None, chroma_dir: str = CHROMA_DATA_DIR):
        self.documents = documents or load_legal_corpus()
        self.chroma_dir = chroma_dir
        self.corpus_texts = [doc.get_search_text() for doc in self.documents]
        
        # 1. BM25 인덱스 빌드
        self.tokenized_corpus = [simple_korean_tokenizer(doc) for doc in self.corpus_texts]
        self.bm25 = BM25Okapi(self.tokenized_corpus)
        
        # 2. Persistent ChromaDB 초기화
        self.chroma_collection = None
        self._init_dense_store()

    def _init_dense_store(self):
        """디스크 영구 저장형(Persistent) ChromaDB 초기화"""
        try:
            import chromadb
            os.makedirs(self.chroma_dir, exist_ok=True)
            client = chromadb.PersistentClient(path=self.chroma_dir)
            self.chroma_collection = client.get_or_create_collection(
                name="korean_all_laws",
                metadata={"hnsw:space": "cosine"}
            )
            
            # 기존 인덱스와 문서 수가 다르면 배치 단위로 안전하게 적재
            if self.chroma_collection.count() != len(self.documents):
                total_docs = len(self.documents)
                print(f"[대용량 배치 인덱싱 시작] 총 {total_docs}건 문서를 250개씩 배치 적재 중 (M1 RAM 최적화)...")
                batch_size = 250
                for i in range(0, total_docs, batch_size):
                    chunk = self.documents[i:i + batch_size]
                    chunk_texts = self.corpus_texts[i:i + batch_size]
                    chunk_ids = [doc.doc_id for doc in chunk]
                    chunk_meta = [
                        {
                            "source": doc.source,
                            "title": doc.title,
                            "doc_type": doc.doc_type,
                            "category": doc.category
                        }
                        for doc in chunk
                    ]
                    self.chroma_collection.upsert(
                        ids=chunk_ids,
                        documents=chunk_texts,
                        metadatas=chunk_meta
                    )
                    print(f" -> [{min(i + batch_size, total_docs)}/{total_docs}] 판례·법령 인덱싱 완료")
                print("[인덱싱 완료] Persistent ChromaDB 대량 적재 성공.")
        except Exception as e:
            print(f"[경고] Dense 인덱스 초기화 오류: {e} -> BM25 전용 모드로 동작")
            self.chroma_collection = None

    def detect_category(self, query: str) -> Optional[str]:
        """질문 속 단어를 분석하여 가장 유력한 법률 분야를 자동 판정"""
        scores = {}
        for cat, keywords in CATEGORY_KEYWORDS.items():
            match_count = sum(1 for kw in keywords if kw in query)
            if match_count > 0:
                scores[cat] = match_count
        if scores:
            best_cat = max(scores.keys(), key=lambda c: scores[c])
            return best_cat
        return None

    def search_bm25(self, query: str, category_filter: Optional[str] = None, top_k: int = 5) -> List[Tuple[LaborLawDocument, float]]:
        """BM25 키워드 검색 (카테고리 필터링 지원)"""
        tokenized_query = simple_korean_tokenizer(query)
        scores = self.bm25.get_scores(tokenized_query)
        
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        results = []
        for idx in ranked_indices:
            doc = self.documents[idx]
            if category_filter and category_filter != "전체" and doc.category != category_filter:
                continue
            results.append((doc, float(scores[idx])))
            if len(results) >= top_k:
                break
        return results

    def search_dense(self, query: str, category_filter: Optional[str] = None, top_k: int = 5) -> List[Tuple[LaborLawDocument, float]]:
        """ChromaDB Dense 검색 (카테고리 메타데이터 필터링 지원)"""
        if not self.chroma_collection:
            return []
        
        where_filter = None
        if category_filter and category_filter != "전체":
            where_filter = {"category": category_filter}

        try:
            results = self.chroma_collection.query(
                query_texts=[query],
                n_results=min(top_k * 2, len(self.documents)),
                where=where_filter
            )
            retrieved_docs = []
            if results and results.get("ids") and len(results["ids"][0]) > 0:
                doc_dict = {d.doc_id: d for d in self.documents}
                for doc_id, dist in zip(results["ids"][0], results["distances"][0]):
                    if doc_id in doc_dict:
                        sim_score = max(0.0, 1.0 - float(dist))
                        retrieved_docs.append((doc_dict[doc_id], sim_score))
                        if len(retrieved_docs) >= top_k:
                            break
            return retrieved_docs
        except Exception:
            return []

    def hybrid_search(self, query: str, category: Optional[str] = "auto", top_k: int = 3, bm25_weight: float = 0.6) -> Tuple[List[Dict[str, Any]], str]:
        """
        2단계 계층적 하이브리드 검색:
        1) 카테고리 자동 판정/필터링
        2) BM25 + Dense RRF 융합 검색
        """
        resolved_category = category
        if category == "auto" or not category:
            detected = self.detect_category(query)
            resolved_category = detected if detected else "전체"

        bm25_results = self.search_bm25(query, category_filter=resolved_category, top_k=top_k * 2)
        dense_results = self.search_dense(query, category_filter=resolved_category, top_k=top_k * 2)

        k_rrf = 60.0
        doc_scores: Dict[str, float] = {}
        doc_map: Dict[str, LaborLawDocument] = {}

        for rank, (doc, _) in enumerate(bm25_results):
            doc_id = doc.doc_id
            doc_map[doc_id] = doc
            doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + (bm25_weight / (k_rrf + rank + 1))

        dense_weight = 1.0 - bm25_weight
        for rank, (doc, _) in enumerate(dense_results):
            doc_id = doc.doc_id
            doc_map[doc_id] = doc
            doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + (dense_weight / (k_rrf + rank + 1))

        if not doc_scores and bm25_results:
            for rank, (doc, _) in enumerate(bm25_results):
                doc_scores[doc.doc_id] = 1.0 / (k_rrf + rank + 1)
                doc_map[doc.doc_id] = doc

        sorted_doc_ids = sorted(doc_scores.keys(), key=lambda did: doc_scores[did], reverse=True)[:top_k]

        final_results = []
        for did in sorted_doc_ids:
            doc = doc_map[did]
            final_results.append({
                "doc_id": doc.doc_id,
                "source": doc.source,
                "title": doc.title,
                "doc_type": doc.doc_type,
                "category": doc.category,
                "content": doc.content,
                "rrf_score": doc_scores[did]
            })

        return final_results, resolved_category


if __name__ == "__main__":
    retriever = HierarchicalLegalRetriever()
    test_queries = [
        "전세계약 만기인데 집주인이 보증금을 안 줘요",
        "음주운전 기준 혈중알코올농도가 얼마인가요?",
        "인터넷 쇼핑몰에서 산 옷 7일 안에 환불 가능한가요?",
        "친구한테 돈 빌려주고 10년 지났는데 받을 수 있나요?"
    ]
    for q in test_queries:
        docs, cat = retriever.hybrid_search(q, category="auto", top_k=2)
        print(f"\n질문: '{q}' [감지된 분야: {cat}]")
        for d in docs:
            print(f" -> [{d['category']}] {d['source']} ({d['title']}) - Score: {d['rrf_score']:.4f}")
