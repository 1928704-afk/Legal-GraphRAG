import legalData from '../../data/legal_bundle.json';

const SYSTEM_PROMPT = `당신은 대한민국 종합 법률(민법, 형법, 주택·상가임대차보호법, 근로기준법, 도로교통법, 전자상거래법 등) 전문 법률 AI 상담 비서입니다.
당신의 임무는 아래 제공된 [참고 법률 및 판례/행정해석]만을 철저히 근거로 삼아, 사용자의 질문에 정확하고 명쾌하게 답변하는 것입니다.

[답변 작성 원칙]
1. [환각 방지]: 반드시 제공된 자료에 기반해서만 답변하고 추측하지 마십시오.
2. [출처 필수 명시]: 법령명과 조항 번호(예: 「주택임대차보호법」 제3조의3) 또는 판례 사건번호(예: 대법원 2021다266631)를 명확히 인용하십시오.
3. [구조화된 설명]: 핵심 결론, 법적 근거 및 실무 유의사항을 순서대로 설명하십시오.
4. [불확실성 안내]: 사실관계에 따라 달라질 수 있는 경우 대한법률구조공단(132) 상담을 안내하십시오.`;

const CATEGORY_KEYWORDS = {
  "부동산/임대차": ["전세", "월세", "보증금", "임대차", "임대인", "임차인", "세입자", "집주인", "계약갱신", "권리금", "상가", "임차권등기", "원상회복"],
  "노동/근로": ["주휴수당", "알바", "퇴직금", "해고", "근로계약", "근로자", "사용자", "통상임금", "연차", "수습", "5인미만", "연장근로"],
  "형사/범죄": ["사기", "고소", "형법", "폭행", "모욕", "명예훼손", "횡령", "배임", "징역", "벌금", "친고죄", "반의사불벌죄", "악플"],
  "교통/사고": ["음주운전", "교통사고", "12대중과실", "뺑소니", "신호위반", "중앙선", "면허", "사고후미조치"],
  "소비자/금융/IT": ["환불", "청약철회", "전자상거래", "최고이자율", "이자제한법", "개인정보", "쇼핑몰", "박스개봉"],
  "민사/계약": ["소멸시효", "채무불이행", "손해배상", "불법행위", "계약금", "해약금", "채권", "빌려", "대여금", "층간소음"]
};

function detectCategory(query) {
  let bestCat = "전체";
  let maxScore = 0;
  for (const [cat, words] of Object.entries(CATEGORY_KEYWORDS)) {
    const score = words.reduce((acc, w) => (query.includes(w) ? acc + 1 : acc), 0);
    if (score > maxScore) {
      maxScore = score;
      bestCat = cat;
    }
  }
  return bestCat;
}

function searchDocs(query, category, topK = 3) {
  const queryTokens = query.toLowerCase().replace(/[^가-힣a-zA-Z0-9]/g, ' ').split(/\s+/).filter(w => w.length >= 2);
  const candidates = legalData.docs.filter(d => {
    if (category && category !== '전체' && category !== 'auto' && d.category !== category) return false;
    return true;
  });

  const scored = candidates.map(doc => {
    const searchTarget = (doc.source + " " + doc.title + " " + doc.content).toLowerCase();
    let score = 0;
    for (const token of queryTokens) {
      if (searchTarget.includes(token)) score += 2;
    }
    return { doc, score };
  });

  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, topK).map(item => ({
    ...item.doc,
    rrf_score: 0.01 + item.score * 0.002
  }));
}

function searchTriples(query, category, topK = 3) {
  const queryTokens = query.toLowerCase().replace(/[^가-힣a-zA-Z0-9]/g, ' ').split(/\s+/).filter(w => w.length >= 2);
  const candidates = legalData.triples.filter(t => {
    if (category && category !== '전체' && category !== 'auto' && t.category && t.category !== category) return false;
    return true;
  });

  const scored = candidates.map(t => {
    const target = (t.subject + " " + t.object + " " + t.predicate + " " + (t.law || "")).toLowerCase();
    let score = 0;
    for (const token of queryTokens) {
      if (t.subject.toLowerCase().includes(token)) score += 3.0;
      else if (target.includes(token)) score += 1.5;
    }
    return { triple: t, score };
  });

  scored.sort((a, b) => b.score - a.score);
  return scored.filter(s => s.score >= 2.0).slice(0, topK).map(s => s.triple);
}

export async function onRequestPost({ request, env }) {
  try {
    const body = await request.json();
    const question = body.question || "";
    let category = body.category || "auto";
    const topK = body.top_k || 3;

    if (category === "auto") {
      category = detectCategory(question);
    }

    // 1. 에지 서버리스 검색 (조문 및 지식 그래프 트리플)
    const retrievedDocs = searchDocs(question, category, topK);
    const graphTriples = searchTriples(question, category, 3);

    // 2. 컨텍스트 구성
    let contextStr = "";
    if (graphTriples.length > 0) {
      contextStr += "【법률 지식 그래프(Knowledge Graph) 인과관계 연결망】\n";
      for (const t of graphTriples) {
        contextStr += `• [${t.subject}] ──(${t.predicate})──> [${t.object}] (근거: ${t.law || ''})\n`;
      }
      contextStr += "\n";
    }

    if (retrievedDocs.length > 0) {
      contextStr += "【관련 법률 조문 및 판례 원문】\n";
      retrievedDocs.forEach((d, idx) => {
        contextStr += `[${idx + 1}] [${d.category}] ${d.source} (${d.title})\n${d.content}\n\n`;
      });
    }

    const promptMessages = [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: `[참고 법률 및 판례]\n${contextStr}\n[사용자 질문]\n${question}\n위 참고 자료를 바탕으로 명확한 출처와 함께 답변해 주세요.` }
    ];

    // SSE 스트림 생성
    const { readable, writable } = new TransformStream();
    const writer = writable.getWriter();
    const encoder = new TextEncoder();

    // 메타데이터 먼저 전송
    const metaPayload = JSON.stringify({ category, docs: retrievedDocs, triples: graphTriples });
    await writer.write(encoder.encode(`event: meta\ndata: ${metaPayload}\n\n`));

    // 3. Cloudflare Workers AI 실행 (또는 스트리밍 fallback)
    (async () => {
      try {
        if (env && env.AI) {
          // Cloudflare Workers AI 서버리스 모델 실행 (@cf/meta/llama-3.1-8b-instruct 또는 @cf/qwen/qwen1.5-7b-chat)
          const responseStream = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
            messages: promptMessages,
            stream: true,
            max_tokens: 1024,
            temperature: 0.1
          });

          const reader = responseStream.getReader();
          const decoder = new TextDecoder();
          let buf = "";

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const lines = buf.split("\n");
            buf = lines.pop();

            for (const line of lines) {
              if (line.startsWith("data: ")) {
                const dataPart = line.replace("data: ", "").trim();
                if (dataPart === "[DONE]") continue;
                try {
                  const parsed = JSON.parse(dataPart);
                  if (parsed.response) {
                    const chunkData = JSON.stringify({ text: parsed.response });
                    await writer.write(encoder.encode(`event: message\ndata: ${chunkData}\n\n`));
                  }
                } catch (e) {}
              }
            }
          }
        } else {
          // Workers AI 바인딩 전 테스트 시 fallback 응답
          const sampleAnswer = `**[결론]** 질문하신 사안에 대해 법률 조문 및 판례를 검토한 결과입니다.\n\n**[법적 근거]**\n- ${retrievedDocs[0] ? retrievedDocs[0].source + '에 의거하여 관련 권리나 의무가 발생합니다.' : '관련 법률 조문 확인이 필요합니다.'}\n\n**[유의사항]** 구체적 사실관계에 따라 결과가 달라질 수 있으므로 법률 전문가(132) 상담을 권장합니다.`;
          const words = sampleAnswer.split(" ");
          for (const w of words) {
            const chunkData = JSON.stringify({ text: w + " " });
            await writer.write(encoder.encode(`event: message\ndata: ${chunkData}\n\n`));
            await new Promise(r => setTimeout(r, 30));
          }
        }

        await writer.write(encoder.encode("event: done\ndata: {}\n\n"));
      } catch (err) {
        const errPayload = JSON.stringify({ text: `\n\n[Cloudflare AI 실행 안내]: ${err.message}` });
        await writer.write(encoder.encode(`event: message\ndata: ${errPayload}\n\n`));
        await writer.write(encoder.encode("event: done\ndata: {}\n\n"));
      } finally {
        await writer.close();
      }
    })();

    return new Response(readable, {
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive"
      }
    });

  } catch (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" }
    });
  }
}
