import os
import json
import re
import networkx as nx
from typing import List, Dict, Any, Optional

TRIPLES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "laws", "legal_triples.json")

def extract_meaningful_tokens(text: str) -> List[str]:
    """2글자 이상의 의미 있는 명사/어절 키워드 추출 (불용어 제외)"""
    words = re.findall(r'[가-힣a-zA-Z0-9]+', text.lower())
    stopwords = {"어떻게", "되나요", "있나요", "인가요", "경우", "관한", "때문", "관련", "대해", "해서", "하면", "안주면", "할때", "기준", "여부"}
    return [w for w in words if len(w) >= 2 and w not in stopwords]


class LegalKnowledgeGraph:
    """
    고정밀 법률 인과관계 지식 그래프 (Knowledge Graph) 엔진
    - 도메인/카테고리 일치 필터링
    - 유효성 임계값(Threshold) 기반 고관련성 트리플만 추출 (노이즈 방지)
    """
    def __init__(self, triples_file: str = TRIPLES_PATH):
        self.triples_file = triples_file
        self.graph = nx.MultiDiGraph()
        self.raw_triples: List[Dict[str, str]] = []
        self.load_graph()

    def load_graph(self):
        """트리플 JSON 파일을 읽어 Directed Graph 구성"""
        self.graph.clear()
        self.raw_triples = []
        
        if os.path.exists(self.triples_file):
            with open(self.triples_file, "r", encoding="utf-8") as f:
                self.raw_triples = json.load(f)
                
            for t in self.raw_triples:
                sub = t["subject"]
                pred = t["predicate"]
                obj = t["object"]
                law = t.get("law", "")
                cat = t.get("category", "")
                
                self.graph.add_node(sub, type="Entity", category=cat)
                self.graph.add_node(obj, type="Value/Concept", category=cat)
                self.graph.add_edge(sub, obj, relation=pred, law=law, category=cat)

    def find_relevant_triples(self, query: str, category: Optional[str] = None, top_k: int = 3, min_score: float = 2.0) -> List[Dict[str, Any]]:
        """
        질문과 진정으로 관련된 트리플만 엄격하게 선별:
        1) 카테고리 필터링: 질문 분야와 일치하는 트리플 우선/한정
        2) 연관도 스코어링: 주어(Subject), 목적어(Object), 법조문과의 직접 키워드 교집합 계산
        3) 임계값 미달 시 과감히 제외 (노이즈 방지)
        """
        query_tokens = extract_meaningful_tokens(query)
        if not query_tokens:
            return []

        scored_candidates = []

        for t in self.raw_triples:
            triple_cat = t.get("category", "")
            
            # 카테고리가 지정되었고 '전체'가 아니라면 해당 분야만 엄격 매칭
            if category and category not in ("auto", "전체") and triple_cat and triple_cat != category:
                continue

            sub_tokens = extract_meaningful_tokens(t["subject"])
            obj_tokens = extract_meaningful_tokens(t["object"])
            pred_tokens = extract_meaningful_tokens(t["predicate"])
            law_tokens = extract_meaningful_tokens(t.get("law", ""))

            score = 0.0

            # 1. Subject 매칭 (가장 높은 가중치)
            for q_tok in query_tokens:
                if any(q_tok in s or s in q_tok for s in sub_tokens):
                    score += 3.0
                elif q_tok in t["subject"]:
                    score += 2.5

            # 2. Object 매칭
            for q_tok in query_tokens:
                if any(q_tok in o or o in q_tok for o in obj_tokens):
                    score += 2.0
                elif q_tok in t["object"]:
                    score += 1.5

            # 3. Predicate 및 Law 매칭
            for q_tok in query_tokens:
                if any(q_tok in p for p in pred_tokens):
                    score += 1.0
                if any(q_tok in l for l in law_tokens):
                    score += 1.5

            # 같은 카테고리 보너스
            if category and triple_cat == category:
                score += 1.0

            # 엄격한 임계값 통과 시에만 후보 등록
            if score >= min_score:
                scored_candidates.append({
                    "triple": {
                        "subject": t["subject"],
                        "predicate": t["predicate"],
                        "object": t["object"],
                        "law": t.get("law", ""),
                        "category": triple_cat
                    },
                    "score": score
                })

        # 점수 순 정렬
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)

        # 상위 top_k만 추출하되, 중복 제거
        results = []
        seen = set()
        for cand in scored_candidates:
            t = cand["triple"]
            key = (t["subject"], t["predicate"], t["object"])
            if key not in seen:
                seen.add(key)
                results.append(t)
                if len(results) >= top_k:
                    break

        return results

    def format_graph_context(self, triples: List[Dict[str, Any]]) -> str:
        """추출된 그래프 트리플들을 LLM 프롬프트용 텍스트로 포맷팅"""
        if not triples:
            return ""

        lines = ["【법률 지식 그래프(Knowledge Graph) 인과관계 연결망】"]
        for t in triples:
            law_citation = f" (법적근거: {t['law']})" if t.get("law") else ""
            line = f"• [{t['subject']}] ──({t['predicate']})──> [{t['object']}]{law_citation}"
            lines.append(line)
            
        return "\n".join(lines)


if __name__ == "__main__":
    kg = LegalKnowledgeGraph()
    test_cases = [
        ("원상회복을 이유로 보증금 반환 거부", "부동산/임대차"),
        ("12시간 알바 주휴수당 미지급", "노동/근로"),
        ("인터넷 롤에서 초성 욕설 고소", "형사/범죄"),
        ("전혀 무관한 우주선 발사 질문", "부동산/임대차")
    ]
    for q, cat in test_cases:
        res = kg.find_relevant_triples(q, category=cat)
        print(f"\n질문: '{q}' (분야: {cat}) -> 추출된 트리플 {len(res)}건:")
        for r in res:
            print(f" -> [{r['subject']}] -({r['predicate']})-> [{r['object']}] ({r['law']})")
