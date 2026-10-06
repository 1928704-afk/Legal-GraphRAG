# ⚖️ 대한민국 대법원 판례·법령 Hybrid GraphRAG 시스템

> 🌐 **실시간 서비스 배포 주소 (Live Demo)**: [https://legal-graphrag.tjsghkwlsgh.workers.dev](https://legal-graphrag.tjsghkwlsgh.workers.dev)  
> 🏛️ **GitHub 저장소**: [https://github.com/1928704-afk/Legal-GraphRAG](https://github.com/1928704-afk/Legal-GraphRAG)

Apple Silicon (M1, 8GB RAM) 환경에 최적화된 **100% 로컬 온디바이스 대한민국 대법원 주요 판례 및 종합 법률 Hybrid GraphRAG**이자, **Cloudflare Workers Edge AI 서버리스로 전 세계 배포 가능한 리걸테크 시스템**입니다.  
단순 법 조항 검색을 넘어 **실제 법원의 판단 기준(판결요지, 입증책임 소재, 인과관계 연결망)**을 공식 공문서 양식인 **「Legal Brief (법률 사실관계 검토의견서)」** 형태로 정밀 진단합니다.

---

## 🌟 핵심 특징

1. **대법원 주요 리딩 판례 대거 탑재 (총 1,091건 법률·판례 코퍼스)**
   - **부동산/임대차**: 집주인 실거주 갱신거절 입증책임(2021다266631), 10년 상가 권리금 보호(2018다242727), 임차권등기 기입 전 이사 위험(2021다219529)
   - **노동/근로**: 통상임금 전원합의체 요건(2013다96390), 퇴직금 1년 직전 고의해고 무효(2020도14896), 포괄임금제 무효(2018다29615)
   - **형사/범죄**: 깡통전세 갭투자 사기죄(2019도11504), 초성 욕설('ㅂㅅ') 모욕죄(2020도11417), 1:1 카톡방 전파가능성 명예훼손(2017도15628)
   - **민사/계약**: 가계약금 파기 시 배액상환 기준(2013다208378), 층간소음 수인한도 초과 위자료(2015다24904), 카톡 독촉 소멸시효 중단(2020다278147)
   - **교통/소비자**: 음주 뺑소니 사고후미조치(2019도10887), 택배 박스 단순 개봉 환불 보장(2018다287114), 최고금리 20% 초과 무효(2020다238914)

2. **Hybrid GraphRAG (Knowledge Graph + Persistent ChromaDB + BM25)**
   - `[주어] ──(법적관계)──▶ [법적효과]` 형태의 인과관계 RDF 트리플과 대법원 판결요지를 융합하여 다단계 추론(Multi-hop Reasoning) 수행.

3. **Legal Brief & Jurisprudence Narrative System UI**
   - **Tactile Judicial Editorialism**: 양식지 질감(`#F9F9F6`), Supreme Navy(`#1B2A4A`), 대법원 직인 인장(Burgundy `#9E2A2B`), Noto Serif KR × Noto Sans KR 서체 적용.
   - **화면 하단부 고정 입력창**: 모바일 및 데스크톱 환경에서 스크롤과 무관하게 언제든 즉시 질의 가능한 하단 고정 바 제공.
   - **Core Web Vitals 최적화**: LCP < 0.1초, CLS = 0.00, INP < 30ms 유지.

4. **하이브리드 듀얼 배포 지원**
   - **로컬 온디바이스**: FastAPI + Ollama (`qwen2.5:3b`) 기반 (API 비용 0원, 오프라인 동작 가능)
   - **클라우드 글로벌 에지**: Cloudflare Workers + Workers AI + Static Assets 기반 초고속 글로벌 서비스

---

## 🚀 빠른 시작

### 1. 배포된 웹 서비스 즉시 이용
별도 설치 없이 브라우저에서 바로 사용하실 수 있습니다:  
👉 **[https://legal-graphrag.tjsghkwlsgh.workers.dev](https://legal-graphrag.tjsghkwlsgh.workers.dev)**

---

### 2. 로컬 온디바이스 실행 (M1 Mac / 로컬 PC)

```bash
# 1. Ollama 모델 준비 (Apple M1 8GB 최적화)
ollama run qwen2.5:3b

# 2. 가상환경 활성화 및 패키지 확인
source .venv/bin/activate

# 3. 로컬 서버 실행
python server.py
```
- 로컬 웹 접속: **`http://localhost:8501`**

---

### 3. Cloudflare Worker 배포

```bash
# 1. Cloudflare 로그인
npx wrangler login

# 2. Worker 및 정적 에셋 한 번에 배포
npx wrangler deploy
```

---

## 📄 라이선스
MIT License
