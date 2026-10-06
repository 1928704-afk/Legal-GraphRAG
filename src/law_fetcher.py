import os
import json
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional

LAWS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "laws")

class LawFetcher:
    """
    국가법령정보센터(law.go.kr) 오픈 API 및 커스텀 법령 데이터를 수집/관리하는 클래스
    """
    def __init__(self, output_dir: str = LAWS_DIR):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def fetch_law_from_api(self, law_name: str, oc_key: str = "test", category: str = "기타") -> Optional[List[Dict[str, Any]]]:
        """
        국가법령정보 공동활용 API (http://www.law.go.kr/DRF/lawSearch.do)를 통해
        법령 XML을 수신하고 [조-항-호] 단위로 파싱하여 JSON으로 저장합니다.
        """
        url = "http://www.law.go.kr/DRF/lawSearch.do"
        params = {
            "OC": oc_key,
            "target": "law",
            "type": "XML",
            "query": law_name
        }

        try:
            res = requests.get(url, params=params, timeout=10)
            res.raise_for_status()
            root = ET.fromstring(res.content)
            
            # 조문 리스트 파싱
            parsed_articles = []
            for article in root.iter("조문단위"):
                art_num = article.findtext("조문번호", "").strip()
                art_title = article.findtext("조문제목", "").strip()
                art_content = article.findtext("조문내용", "").strip()
                
                if art_content:
                    parsed_articles.append({
                        "law_name": law_name,
                        "article_number": f"제{art_num}조" if art_num and not art_num.startswith("제") else art_num,
                        "title": art_title or "조문",
                        "category": category,
                        "content": art_content
                    })

            if parsed_articles:
                filename = f"{law_name.replace(' ', '_')}.json"
                save_path = os.path.join(self.output_dir, filename)
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(parsed_articles, f, ensure_ascii=False, indent=2)
                print(f"[수집 완료] {law_name}: 총 {len(parsed_articles)}개 조문 저장 -> {save_path}")
                return parsed_articles

        except Exception as e:
            print(f"[알림] Open API 직접 수집 실패 ({e}). 오프라인 데이터셋 또는 로컬 파일 생성을 지원합니다.")
            return None

    def add_custom_law_article(self, law_name: str, article_number: str, title: str, category: str, content: str):
        """특정 법률 조문을 수동 또는 커스텀으로 추가할 때 사용하는 헬퍼"""
        file_path = os.path.join(self.output_dir, f"{category.replace('/', '_')}.json")
        items = []
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                items = json.load(f)

        new_item = {
            "law_name": law_name,
            "article_number": article_number,
            "title": title,
            "category": category,
            "content": content
        }
        items.append(new_item)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print(f"[추가 완료] {law_name} {article_number} ({title}) -> {file_path}")


if __name__ == "__main__":
    fetcher = LawFetcher()
    print("LawFetcher initialized. Target directory:", LAWS_DIR)
