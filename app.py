import streamlit as st
import os
import sys

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.pipeline import LaborLawRAGPipeline

st.set_page_config(
    page_title="노동법 AI 법률 상담기 (RAG)",
    page_icon="⚖️",
    layout="wide"
)

# 커스텀 스타일
st.markdown("""
<style>
    .source-box {
        background-color: #f8f9fa;
        border-left: 4px solid #1f77b4;
        padding: 10px 15px;
        margin-bottom: 10px;
        border-radius: 4px;
        font-size: 0.9em;
    }
    .badge-law {
        background-color: #007bff;
        color: white;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.75em;
        font-weight: bold;
    }
    .badge-precedent {
        background-color: #28a745;
        color: white;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.75em;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# 파이프라인 캐싱
@st.cache_resource(show_spinner="법률 데이터 및 RAG 엔진 초기화 중...")
def get_pipeline(model_name: str):
    return LaborLawRAGPipeline(model_name=model_name)

# 사이드바 설정
with st.sidebar:
    st.header("⚙️ RAG 시스템 설정")
    
    model_name = st.text_input("Ollama 모델명", value="qwen2.5:3b", help="로컬 Ollama에 설치된 모델명을 입력하세요.")
    top_k = st.slider("검색 상위 문서 수 (Top-K)", min_value=1, max_value=5, value=3, help="LLM에 전달할 근거 문서 개수입니다. 3B 모델은 2~3개가 적절합니다.")
    bm25_weight = st.slider("BM25 가중치 (0=Dense, 1=BM25)", min_value=0.0, max_value=1.0, value=0.6, step=0.1, help="조문 번호나 키워드 정확도를 높이려면 0.5~0.7을 추천합니다.")
    
    st.markdown("---")
    st.subheader("💡 빠른 질문 예시")
    sample_questions = [
        "주휴수당 15시간 미만 알바도 받을 수 있나요?",
        "수습 2개월차인데 구두로 해고 통보를 받았습니다. 정당한가요?",
        "5인 미만 사업장에서도 연차휴가와 부당해고 구제가 적용되나요?",
        "퇴직금 받으려면 근무 기간과 근로시간 조건이 어떻게 되나요?",
        "야간근로(오후 10시~오전 6시) 가산수당 기준이 어떻게 되나요?"
    ]
    
    for sq in sample_questions:
        if st.button(sq, use_container_width=True):
            st.session_state["preset_input"] = sq

    st.markdown("---")
    st.caption("🔒 100% On-Device Local RAG | Apple Silicon M1 최적화")

# 메인 타이틀
st.title("⚖️ 소상공인·근로자를 위한 노동법 AI 상담 (Local RAG)")
st.caption("근로기준법, 퇴직급여보장법, 고용노동부 행정해석 및 대법원 판례 기반 팩트 체크")

# 경고 문구
st.warning("⚠️ **주의**: 본 시스템의 답변은 참고용 정보이며 공식 법적 효력이 없습니다. 구체적인 권리 구제나 분쟁은 공인노무사 또는 고용노동부(국번없이 1350)에 문의하세요.", icon="📌")

# 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state["messages"] = []

# 대화 기록 표시
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "docs" in msg and msg["docs"]:
            with st.expander("📚 답변에 인용된 법률 및 판례 근거 확인"):
                for d in msg["docs"]:
                    badge_class = "badge-law" if d["doc_type"] == "법령" else "badge-precedent"
                    st.markdown(f"""
                    <div class="source-box">
                        <span class="{badge_class}">{d['doc_type']}</span> <strong>{d['source']}</strong> - {d['title']} (RRF Score: {d['rrf_score']:.4f})
                        <br><br>
                        <pre style="white-space: pre-wrap; font-family: inherit;">{d['content']}</pre>
                    </div>
                    """, unsafe_allow_html=True)

# 질문 입력 처리
user_input = st.chat_input("노동법 관련 질문을 입력하세요 (예: 주 14시간 알바 주휴수당)")
if "preset_input" in st.session_state and st.session_state["preset_input"]:
    user_input = st.session_state["preset_input"]
    st.session_state["preset_input"] = None

if user_input:
    # 1. 사용자 메시지 등록
    st.session_state["messages"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # 2. RAG 파이프라인 호출
    pipeline = get_pipeline(model_name)
    
    with st.chat_message("assistant"):
        with st.spinner("관련 조문 및 판례 검색 중..."):
            retrieved_docs, stream_gen = pipeline.ask_stream(
                question=user_input,
                top_k=top_k,
                bm25_weight=bm25_weight
            )

        # 스트리밍 출력
        response_placeholder = st.empty()
        full_response = ""
        for chunk in stream_gen:
            full_response += chunk
            response_placeholder.markdown(full_response + "▌")
        response_placeholder.markdown(full_response)

        # 근거 문서 출력
        if retrieved_docs:
            with st.expander("📚 답변에 인용된 법률 및 판례 근거 확인"):
                for d in retrieved_docs:
                    badge_class = "badge-law" if d["doc_type"] == "법령" else "badge-precedent"
                    st.markdown(f"""
                    <div class="source-box">
                        <span class="{badge_class}">{d['doc_type']}</span> <strong>{d['source']}</strong> - {d['title']} (RRF Score: {d['rrf_score']:.4f})
                        <br><br>
                        <pre style="white-space: pre-wrap; font-family: inherit;">{d['content']}</pre>
                    </div>
                    """, unsafe_allow_html=True)

    # 메시지 기록 저장
    st.session_state["messages"].append({
        "role": "assistant",
        "content": full_response,
        "docs": retrieved_docs
    })
