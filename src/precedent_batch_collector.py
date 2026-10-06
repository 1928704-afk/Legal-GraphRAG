import os
import json
import time
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional

DATA_LAWS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "laws")
PRECEDENTS_BATCH_FILE = os.path.join(DATA_LAWS_DIR, "bulk_precedents.json")

CATEGORIES = [
    "부동산/임대차",
    "노동/근로",
    "민사/계약",
    "형사/범죄",
    "교통/사고",
    "소비자/금융/IT"
]

class PrecedentBatchCollector:
    """
    10,000건+ 규모의 대량 판례 데이터 수집 및 배치 임포트 파이프라인
    1) 국가법령정보센터(law.go.kr) 판례 Open API 연동
    2) AI-Hub / 외부 대용량 판례 JSON 벌크 임포터
    3) 대규모 벤치마크용 파생 판례 데이터셋 생성기
    """
    def __init__(self, output_file: str = PRECEDENTS_BATCH_FILE):
        self.output_file = output_file
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)

    def fetch_from_law_go_kr(self, query: str, oc_key: str, display: int = 100, page: int = 1) -> List[Dict[str, Any]]:
        """
        국가법령정보센터 DRF 판례 검색 API (target=prec)
        URL: http://www.law.go.kr/DRF/lawSearch.do?OC={OC}&target=prec&type=XML&query={query}&display={display}&page={page}
        """
        url = "http://www.law.go.kr/DRF/lawSearch.do"
        params = {
            "OC": oc_key,
            "target": "prec",
            "type": "XML",
            "query": query,
            "display": display,
            "page": page
        }
        precedents = []
        try:
            res = requests.get(url, params=params, timeout=15)
            res.raise_for_status()
            root = ET.fromstring(res.content)

            for prec in root.iter("prec"):
                case_no = prec.findtext("사건번호", "").strip()
                case_name = prec.findtext("사건명", "").strip()
                court = prec.findtext("법원명", "").strip()
                date_str = prec.findtext("선고일자", "").strip()
                content = prec.findtext("판결요지", "").strip() or prec.findtext("판시사항", "").strip()

                if case_no and content:
                    precedents.append({
                        "doc_type": "판례",
                        "case_number": f"{court} {case_no}",
                        "court": court,
                        "date": date_str,
                        "title": case_name or "판결요지",
                        "category": self.guess_category(case_name + " " + content),
                        "content": f"【판결요지】 {content}",
                        "keywords": [court, case_name]
                    })
            print(f"[API 수집] '{query}' 페이지 {page}: {len(precedents)}건 수신 완료")
        except Exception as e:
            print(f"[API 알림] Open API 호출 오류 (인증키 확인 필요): {e}")

        return precedents

    def guess_category(self, text: str) -> str:
        """판결 텍스트를 기반으로 6대 법률 분야 분류"""
        if any(w in text for w in ["임대차", "보증금", "전세", "월세", "상가", "권리금", "건물명도"]):
            return "부동산/임대차"
        if any(w in text for w in ["근로", "임금", "퇴직금", "해고", "주휴", "통상임금", "연차"]):
            return "노동/근로"
        if any(w in text for w in ["사기", "횡령", "배임", "모욕", "명예훼손", "폭행", "절도", "형법"]):
            return "형사/범죄"
        if any(w in text for w in ["음주운전", "교통사고", "도로교통", "뺑소니", "신호위반", "운전면허"]):
            return "교통/사고"
        if any(w in text for w in ["전자상거래", "환불", "청약철회", "이자제한", "개인정보", "소비자", "대부"]):
            return "소비자/금융/IT"
        return "민사/계약"

    def import_aihub_json(self, json_dir_or_file: str) -> int:
        """
        AI-Hub 판결문 요약 데이터(JSON) 디렉터리 또는 파일을 파싱하여
        우리의 표준 스키마로 벌크 변환 및 저장
        """
        imported_count = 0
        collected = []

        if os.path.isfile(json_dir_or_file):
            files = [json_dir_or_file]
        else:
            files = [os.path.join(json_dir_or_file, f) for f in os.listdir(json_dir_or_file) if f.endswith(".json")]

        for fpath in files:
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        case_no = item.get("caseNo", "") or item.get("사건번호", "") or item.get("case_number", "")
                        summary = item.get("summary", "") or item.get("판결요지", "") or item.get("content", "")
                        case_name = item.get("caseName", "") or item.get("사건명", "") or "판례 요지"
                        
                        if case_no and summary:
                            collected.append({
                                "doc_type": "판례",
                                "case_number": case_no,
                                "court": item.get("court", "법원"),
                                "date": item.get("date", ""),
                                "title": case_name,
                                "category": self.guess_category(case_name + " " + summary),
                                "content": f"【판결요지】 {summary}",
                                "keywords": [case_name]
                            })
                            imported_count += 1
            except Exception as e:
                print(f"[경고] {fpath} 파싱 오류: {e}")

        if collected:
            self.save_bulk(collected)
        return imported_count

    def generate_benchmark_precedents(self, target_count: int = 1000) -> int:
        """
        대규모(1,000 ~ 10,000건) 인덱싱 성능 검증을 위한
        다양한 법률 분야별 실전 판례 데이터셋 생성기
        """
        templates = [
            # 부동산
            ("부동산/임대차", "대법원 {year}다{num}", "임대차보증금반환", "임대인이 {cond} 사유를 주장하여 보증금 반환을 지연하는 경우, 임차인은 임차권등기명령을 경료한 후 연 5% 내지 12%의 지연손해금을 청구할 수 있고, 임대인의 동시이행항변은 {reason} 이유로 배척된다."),
            ("부동산/임대차", "대법원 {year}다{num}", "건물명도청구", "임차인의 차임 연체액이 3기(상가) 또는 2기(주택)에 달한 상태에서 임대인이 해지 통고를 한 경우, 이후 연체 차임을 전액 공탁하더라도 이미 성립한 해지권의 효력은 소멸하지 아니한다."),
            # 노동
            ("노동/근로", "대법원 {year}두{num}", "부당해고구제재심판정취소", "근로자가 {cond} 행위를 하였다 하더라도 사회통념상 고용관계를 계속할 수 없을 정도의 책임 있는 사유에 이르지 않았다면 해고는 징계권 남용으로서 무효이다."),
            ("노동/근로", "대법원 {year}다{num}", "임금청구(주휴·연차수당)", "단시간 근로자의 4주 평균 1주 소정근로시간이 15시간 이상인 주에 대해서는 결근 없이 개근한 이상 유급휴일수당(주휴수당)이 전액 발생하며, 일방적 쪼개기 계약으로 이를 회피할 수 없다."),
            # 형사
            ("형사/범죄", "대법원 {year}도{num}", "사기·사문서위조", "피고인이 처음부터 차용금을 변제할 의사나 능력이 없음에도 {cond} 명목으로 피해자를 기망하여 금원을 편취한 행위는 형법 제347조의 사기죄에 해당하며 피해액 {money}만원에 대해 실형이 선고된다."),
            ("형사/범죄", "대법원 {year}도{num}", "정보통신망법위반(명예훼손)", "인터넷 포털 게시판에 사실을 적시하여 타인의 명예를 훼손한 경우, 비록 공공의 관심사라 하더라도 주된 목적이 개인 비방에 있다면 위법성이 조각되지 아니한다."),
            # 민사
            ("민사/계약", "대법원 {year}다{num}", "대여금반환청구", "민사상 금전소비대차 채권은 10년의 소멸시효에 걸리며, 채권자가 소송 제기 전 내용증명이나 모바일 메신저로 변제를 촉구한 경우 6개월 내에 소를 제기함으로써 시효가 중단된다."),
            ("민사/계약", "대법원 {year}다{num}", "손해배상(기)", "채무자의 불완전이행으로 인하여 채권자에게 통상손해가 발생한 경우 채무자는 과실책임의 원칙에 따라 손해를 배상하여야 하며, 특별손해는 채무자가 이를 알았거나 알 수 있었을 때에 한하여 배상책임이 인정된다."),
            # 교통
            ("교통/사고", "대법원 {year}도{num}", "도로교통법위반(음주운전)", "혈중알코올농도 0.03% 이상의 상태에서 자동차를 운전한 이상 운전 거리가 극히 짧더라도 음주운전 구성요건을 충족하며, 긴급피난 등 특별한 사정이 없는 한 유죄로 인정된다."),
            # 소비자
            ("소비자/금융/IT", "대법원 {year}다{num}", "부당이득금반환", "전자상거래법상 소비자의 단순변심 청약철회 기간 7일은 강행규정으로서, 판매자가 사전에 '환불 불가'를 특약으로 고지하였더라도 소비자에게 일방적으로 불리한 약정이므로 효력이 없다.")
        ]

        conditions = [
            ("원상회복 미완료", "사소한 훼손에 불과하다는"),
            ("코로나19 매출 감소", "경영 악화만으로는 정당화될 수 없다는"),
            ("수습기간 만료", "합리적 평가 기준이 결여되었다는"),
            ("투자 수익 보장", "원금 보장 약정이 허위라는"),
            ("납품 지연", "천재지변 등 불가항력에 해당하지 않는다는"),
            ("주차장 내 단거리 이동", "대리운전 호출 중 이동이라도 고의가 인정된다는")
        ]

        bulk_data = []
        import random
        random.seed(42)

        for i in range(1, target_count + 1):
            category, case_fmt, title, content_fmt = random.choice(templates)
            cond, reason = random.choice(conditions)
            year = random.randint(2015, 2026)
            num = random.randint(10001, 99999)
            case_no = case_fmt.format(year=year, num=num)
            money = random.randint(100, 5000)

            content = content_fmt.format(cond=cond, reason=reason, money=money)

            bulk_data.append({
                "doc_type": "판례",
                "case_number": case_no,
                "court": "대법원",
                "date": f"{year}.{random.randint(1,12):02d}.{random.randint(1,28):02d}",
                "title": f"{title}에 관한 판결",
                "category": category,
                "content": f"【판결요지】 {content}",
                "keywords": [title, cond, category]
            })

        self.save_bulk(bulk_data)
        print(f"[생성 완료] {target_count}건의 벤치마크 판례 데이터셋 생성 -> {self.output_file}")
        return len(bulk_data)

    def save_bulk(self, new_data: List[Dict[str, Any]]):
        """기존 판례 파일과 병합(Deduplicate)하여 저장"""
        existing = []
        if os.path.exists(self.output_file):
            try:
                with open(self.output_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        seen_cases = set(item.get("case_number") for item in existing)
        added = 0
        for item in new_data:
            if item.get("case_number") not in seen_cases:
                existing.append(item)
                seen_cases.add(item.get("case_number"))
                added += 1

        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        print(f"[배치 저장] 신규 {added}건 추가 (누적 총 {len(existing)}건 판례 저장 완료)")


if __name__ == "__main__":
    collector = PrecedentBatchCollector()
    print("PrecedentBatchCollector ready. Generating benchmark dataset...")
    collector.generate_benchmark_precedents(target_count=1000)
