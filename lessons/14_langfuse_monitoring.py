"""Lesson 14 — Langfuse를 통한 LLM 모니터링 실무 연동

## Langfuse란?
LLM 기반 서비스의 개발·운영 전 과정을 추적하고 관리하는 오픈소스 Observability 플랫폼입니다.
일반 웹 서비스에서 Datadog을 쓰듯, LLM 앱의 성능·비용·프롬프트 품질 관리에 사용합니다.

## 4가지 핵심 기능
1. Tracing   — 요청~응답 전 단계(RAG, 프롬프트 조립, API 호출)를 타임라인으로 시각화
2. Cost      — 모델별 토큰 수를 집계하고 USD 비용으로 환산
3. Prompts   — 프롬프트를 버전별로 중앙 관리, 코드 재배포 없이 교체
4. Eval      — 사용자 피드백(좋아요/싫어요) 및 LLM-as-Judge 자동 평가

## 사전 준비
pip install langfuse openai

.env 설정:
  LANGFUSE_SECRET_KEY=sk-lf-...
  LANGFUSE_PUBLIC_KEY=pk-lf-...
  LANGFUSE_HOST=https://cloud.langfuse.com

실행:
  docker compose run --rm lab python lessons/14_langfuse_monitoring.py
"""
from __future__ import annotations
import os, time, json, re
from rich import print
from rich.rule import Rule
from lessons._utils import header, show_provider
from app.core.llm_factory import build_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage

try:
    from langfuse import Langfuse
    from langfuse.decorators import observe, langfuse_context
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False

# ════════════════════════════════════════════════════════════════════════════
# §1 환경 확인
# ════════════════════════════════════════════════════════════════════════════

def _langfuse_ready() -> bool:
    if not LANGFUSE_AVAILABLE:
        print("[yellow]⚠ langfuse 미설치[/yellow] — pip install langfuse")
        return False
    if not os.getenv("LANGFUSE_SECRET_KEY"):
        print("[yellow]⚠ LANGFUSE_SECRET_KEY 미설정[/yellow] — .env를 확인하세요.")
        return False
    return True


# ════════════════════════════════════════════════════════════════════════════
# §2 Tracing — @observe 데코레이터로 RAG 파이프라인 추적
# ════════════════════════════════════════════════════════════════════════════

DEMO_CONTEXT = (
    "LangChain Expression Language(LCEL)는 체인을 선언적으로 구성하는 방법입니다. "
    "파이프(|) 연산자로 Runnable 객체를 연결하며 스트리밍·배치·비동기를 지원합니다. "
    "각 Runnable은 invoke / batch / stream 인터페이스를 공유합니다."
)


def _build_rag_pipeline(lf: "Langfuse | None"):
    """lf가 None이면 데코레이터 없이, 있으면 @observe로 래핑된 함수를 반환합니다."""
    llm = build_chat_model(temperature=0)

    def _retrieval(query: str) -> str:
        # 실제 프로젝트에서는 ChromaDB/FAISS 검색
        return DEMO_CONTEXT

    def _generate(context: str, query: str) -> str:
        prompt = ChatPromptTemplate.from_messages([
            ("system", "컨텍스트 정보만 사용해서 답하세요.\n\n컨텍스트:\n{context}"),
            ("human", "{query}"),
        ])
        resp = (prompt | llm).invoke({"context": context, "query": query})
        return getattr(resp, "content", str(resp))

    if lf is None:
        def rag_pipeline(query: str) -> str:
            ctx = _retrieval(query)
            return _generate(ctx, query)
        return rag_pipeline

    @observe()
    def retrieval(query: str) -> str:
        langfuse_context.update_current_observation(name="retrieval", input={"query": query})
        result = _retrieval(query)
        langfuse_context.update_current_observation(output=result)
        return result

    @observe()
    def generation(context: str, query: str) -> str:
        langfuse_context.update_current_observation(name="llm_call")
        result = _generate(context, query)
        langfuse_context.update_current_observation(output=result)
        return result

    @observe()
    def rag_pipeline(query: str) -> str:
        langfuse_context.update_current_trace(
            name="lesson14-rag",
            user_id="lesson14-user",
            tags=["lesson14", "rag"],
        )
        ctx = retrieval(query)
        return generation(ctx, query)

    return rag_pipeline


# ════════════════════════════════════════════════════════════════════════════
# §3 Cost Tracking — generation span에 토큰 수 직접 기록
# ════════════════════════════════════════════════════════════════════════════

def _cost_demo(lf: "Langfuse"):
    llm = build_chat_model(temperature=0)
    trace = lf.trace(name="lesson14-cost", tags=["lesson14", "cost"])

    prompts = [
        "LCEL의 장점을 한 문장으로 설명해줘.",
        "LangChain 에이전트란 무엇인가요?",
    ]

    for i, p in enumerate(prompts):
        t0 = time.time()
        resp = llm.invoke([HumanMessage(content=p)])
        elapsed = round(time.time() - t0, 2)

        usage = getattr(resp, "usage_metadata", None) or {}
        in_tok = usage.get("input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)

        trace.generation(
            name=f"call-{i+1}",
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            input=[{"role": "user", "content": p}],
            output=getattr(resp, "content", str(resp)),
            usage={"input": in_tok, "output": out_tok, "unit": "TOKENS"},
            metadata={"elapsed_s": elapsed},
        )
        print(f"  call-{i+1}: in={in_tok} out={out_tok} tok, {elapsed}s")


# ════════════════════════════════════════════════════════════════════════════
# §4 Prompt Management — Langfuse에서 프롬프트 버전을 가져와 실행
# ════════════════════════════════════════════════════════════════════════════

FALLBACK_SYSTEM = (
    "당신은 {domain} 분야의 전문 어시스턴트입니다.\n"
    "컨텍스트 정보만 사용해서 답하세요."
)


def _prompt_demo(lf: "Langfuse", query: str) -> str:
    llm = build_chat_model(temperature=0)

    try:
        lf_prompt = lf.get_prompt("rag-system-prompt")
        system_text = lf_prompt.compile(domain="소프트웨어 개발")
        print(f"  [green]프롬프트 로드됨[/green] (v{lf_prompt.version})")
    except Exception:
        system_text = FALLBACK_SYSTEM.format(domain="소프트웨어 개발")
        lf_prompt = None
        print("  [dim]폴백 프롬프트 사용 중[/dim]")

    @observe()
    def call(sys: str, ctx: str, q: str) -> str:
        if lf_prompt:
            langfuse_context.update_current_observation(prompt=lf_prompt)
        pt = ChatPromptTemplate.from_messages([
            ("system", sys),
            ("human", "컨텍스트:\n{context}\n\n질문: {query}"),
        ])
        r = (pt | llm).invoke({"context": ctx, "query": q})
        return getattr(r, "content", str(r))

    return call(system_text, DEMO_CONTEXT, query)


# ════════════════════════════════════════════════════════════════════════════
# §5 Evaluation — LLM-as-Judge 채점 후 Score 기록
# ════════════════════════════════════════════════════════════════════════════

JUDGE_PROMPT = """다음 기준으로 답변을 0~1 점수로 평가하고 JSON으로만 응답하세요.
grounding: 답변이 컨텍스트에만 근거하는가 (1=완전 근거, 0=환각)
relevance: 질문에 정확히 답하는가 (1=완전 관련)

{"grounding": <0~1>, "relevance": <0~1>, "reason": "<근거>"}"""


def _judge(question: str, context: str, answer: str) -> dict:
    llm = build_chat_model(temperature=0)
    raw = llm.invoke([
        SystemMessage(content=JUDGE_PROMPT),
        HumanMessage(content=f"질문: {question}\n\n컨텍스트: {context}\n\n답변: {answer}"),
    ])
    text = getattr(raw, "content", str(raw))
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {"grounding": 0.5, "relevance": 0.5, "reason": "파싱 실패"}


def _eval_demo(lf: "Langfuse", query: str, answer: str):
    scores = _judge(query, DEMO_CONTEXT, answer)
    g, r = scores.get("grounding", 0), scores.get("relevance", 0)
    g_color = "green" if g >= 0.7 else "red"
    r_color = "green" if r >= 0.7 else "yellow"
    print(f"  grounding=[{g_color}]{g}[/{g_color}]  relevance=[{r_color}]{r}[/{r_color}]")
    print(f"  근거: {scores.get('reason')}")

    traces = lf.fetch_traces(name="lesson14-rag", limit=1).data
    if traces:
        tid = traces[0].id
        lf.score(trace_id=tid, name="grounding", value=g, comment=scores.get("reason", ""))
        lf.score(trace_id=tid, name="relevance", value=r)
        lf.score(trace_id=tid, name="user_feedback", value=1, data_type="BOOLEAN",
                 comment="시뮬레이션: 좋아요")
        print(f"  [green]Score 기록 완료 (trace: {tid[:8]}...)[/green]")


# ════════════════════════════════════════════════════════════════════════════
# main
# ════════════════════════════════════════════════════════════════════════════

def main():
    header("14) Langfuse LLM 모니터링 실무 연동")
    show_provider()

    query = "LangChain LCEL의 핵심 특징을 알려줘."

    # ── §2 Tracing (Langfuse 없이도 동작) ─────────────────────────────────
    print(Rule("[bold]§2 Tracing[/bold]"))
    ready = _langfuse_ready()
    lf = Langfuse() if ready else None

    pipeline = _build_rag_pipeline(lf)
    answer = pipeline(query)
    print(f"[bold]답변:[/bold] {answer[:200]}...")

    if not ready:
        print("[dim]Langfuse 미연결 — 나머지 섹션을 건너뜁니다.[/dim]")
        _print_setup_guide()
        return

    lf.flush()
    print("[green]✓ Trace 전송 완료[/green]")

    # ── §3 Cost Tracking ───────────────────────────────────────────────────
    print(Rule("[bold]§3 Cost Tracking[/bold]"))
    _cost_demo(lf)
    lf.flush()
    print("[green]✓ generation span 기록 완료[/green]")

    # ── §4 Prompt Management ───────────────────────────────────────────────
    print(Rule("[bold]§4 Prompt Management[/bold]"))
    answer2 = _prompt_demo(lf, query)
    lf.flush()
    print(f"[bold]답변:[/bold] {answer2[:150]}...")

    # ── §5 Evaluation ──────────────────────────────────────────────────────
    print(Rule("[bold]§5 Evaluation (LLM-as-Judge)[/bold]"))
    _eval_demo(lf, query, answer)
    lf.flush()

    print(Rule())
    print("[bold cyan]→ Langfuse 대시보드에서 결과를 확인하세요.[/bold cyan]")
    print("  • Traces  : lesson14-rag, lesson14-cost")
    print("  • Scores  : grounding / relevance / user_feedback")
    print("  • Prompts : rag-system-prompt (버전 사용 기록)")


def _print_setup_guide():
    print("\n[bold]Langfuse 연동 빠른 시작:[/bold]")
    print("  1. https://cloud.langfuse.com 가입 후 프로젝트 생성")
    print("  2. Settings → API Keys → Secret/Public Key 발급")
    print("  3. .env 파일에 추가:")
    print("     [cyan]LANGFUSE_SECRET_KEY=sk-lf-...[/cyan]")
    print("     [cyan]LANGFUSE_PUBLIC_KEY=pk-lf-...[/cyan]")
    print("  4. pip install langfuse")
    print("  5. 이 파일을 다시 실행하면 Traces가 대시보드에 표시됩니다.")
    print("\n  catalog/monitoring/ 에서 기능별 상세 예제를 확인하세요.")


if __name__ == "__main__":
    main()
