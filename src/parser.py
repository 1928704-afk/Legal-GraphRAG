import json
import os
import glob
from typing import List, Dict, Any, Set

class LaborLawDocument:
    def __init__(self, doc_id: str, doc_type: str, source: str, title: str, content: str, category: str = "기타", keywords: List[str] = None):
        self.doc_id = doc_id
        self.doc_type = doc_type  # '법령', '행정해석', '판례'
        self.source = source      # e.g., '주택임대차보호법 제3조', '근로기준법 제55조'
        self.title = title
        self.content = content
        self.category = category  # e.g., '부동산/임대차', '민사/계약', '형사/범죄'
        self.keywords = keywords or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "doc_type": self.doc_type,
            "source": self.source,
            "title": self.title,
            "category": self.category,
            "content": self.content,
            "keywords": self.keywords,
            "search_text": self.get_search_text()
        }

    def get_search_text(self) -> str:
        kw_str = " ".join(self.keywords) if self.keywords else ""
        return f"[{self.category}] [{self.source}] {self.title}\n{self.content}\n키워드: {kw_str}".strip()


def load_legal_corpus(base_dir: str = None) -> List[LaborLawDocument]:
    """
    data/laws 및 data/raw 디렉터리 내의 모든 법령/판례 데이터를 동적으로 로드합니다.
    """
    if base_dir is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    documents: List[LaborLawDocument] = []
    doc_counter = 1

    # 1. data/laws/ 디렉터리의 모든 법률 JSON 파일 로드
    laws_pattern = os.path.join(base_dir, "data", "laws", "*.json")
    for file_path in glob.glob(laws_pattern):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                items = json.load(f)
                for item in items:
                    doc_type = item.get("doc_type", "법령")
                    if doc_type == "판례" or "case_number" in item:
                        source = item.get("case_number", "대법원 판례")
                        doc_type = "판례"
                    else:
                        law_name = item.get("law_name", "법률")
                        art_num = item.get("article_number", "")
                        source = f"{law_name} {art_num}".strip()

                    cat = item.get("category", "일반법")
                    labor_subcategories = {"총칙", "근로계약", "단시간근로", "해고", "임금", "근로시간", "휴게", "휴일/주휴수당", "가산수당", "연차휴가", "퇴직금", "최저임금"}
                    primary_cat = "노동/근로" if cat in labor_subcategories else cat

                    doc = LaborLawDocument(
                        doc_id=f"doc_{doc_counter:04d}",
                        doc_type=doc_type,
                        source=source,
                        title=item.get("title", ""),
                        content=item.get("content", ""),
                        category=primary_cat,
                        keywords=[primary_cat, cat, source] + item.get("keywords", [])
                    )
                    documents.append(doc)
                    doc_counter += 1
        except Exception as e:
            print(f"[경고] {file_path} 로드 실패: {e}")

    # 2. 행정해석 및 판례 데이터 로드
    precedents_path = os.path.join(base_dir, "data", "raw", "labor_precedents.json")
    if os.path.exists(precedents_path):
        try:
            with open(precedents_path, "r", encoding="utf-8") as f:
                precedents = json.load(f)
                for item in precedents:
                    source = f"{item['type']} {item['case_number']}"
                    doc = LaborLawDocument(
                        doc_id=f"doc_{doc_counter:04d}",
                        doc_type=item["type"],
                        source=source,
                        title=item["title"],
                        content=item["content"],
                        category="노동/근로",
                        keywords=item.get("keywords", [])
                    )
                    documents.append(doc)
                    doc_counter += 1
        except Exception as e:
            print(f"[경고] {precedents_path} 로드 실패: {e}")

    return documents


def get_all_categories(docs: List[LaborLawDocument]) -> List[str]:
    cats: Set[str] = set(doc.category for doc in docs)
    return sorted(list(cats))


if __name__ == "__main__":
    docs = load_legal_corpus()
    print(f"총 {len(docs)}건의 종합 법률 문서 로드 완료!")
    categories = get_all_categories(docs)
    print("탑재된 법률 분야:", categories)
    for c in categories:
        count = sum(1 for d in docs if d.category == c)
        print(f" - {c}: {count}개 조문")
