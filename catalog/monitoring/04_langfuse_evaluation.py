"""Monitoring 04 — Langfuse 답변 품질 평가 (Score)

Langfuse에서 평가(Evaluation)는 Trace에 Score를 붙이는 행위입니다.
크게 두 가지 방법이 있습니다:

1. 사용자 피드백 Score: 좋아요/싫어요 등 실서비스 사용자 반응을 기록
2. LLM-as-Judge Score: 다른 LLM이 답변을 자동으로 채점 (Hallucination 검사 등)

이 파일은 두 방법 모두를 시연합니다.

실행:
  docker compose run --rm lab python catalog/monitoring/04_langfuse_evaluation.py
"""
from __future__ import annotations
import os
from rich import print
from rich.panel import Panel
from app.utils.console import header
from app.core.llm_factory import build_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

try:
    from langfuse import Langfuse
    from langfuse.decorators import observe, langfuse_context
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False


# ── LLM-as-Judge 평가 로직 ─────────────────────────────────────────────────

JUDGE_SYSTEM = """당신은 LLM 답변의 품질을 평가하는 심사 AI입니다.
주어진 질문, 컨텍스트, 답변을 보고 다음 기준으로 0~1 사이의 점수와 근거를 제시하세요.

평가 기준:
- grounding(근거 충실도): 답변이 컨텍스트에 있는 정보에만 기반하는가? (1=완전 근거, 0=환각)
- relevance(관련성): 답변이 질문에 정확히 답하는가? (1=완전 관련, 0=무관)

응답 형식 (JSON만 출력):
{"grounding": <0~1>, "relevance": <0~1>, "reason": "<한 문장 근거>"}
"""


def _llm_judge(question: str, context: str, answer: str) -> dict:
    """LLM-as-Judge 패턴으로 답변을 자동 평가합니다."""
    judge_llm = build_chat_model(temperature=0)

    user_content = (
        f"[질문]\n{question}\n\n"
        f"[컨텍스트]\n{context}\n\n"
        f"[답변]\n{answer}"
    )

    resp = judge_llm.invoke([
        SystemMessage(content=JUDGE_SYSTEM),
        HumanMessage(content=user_content),
    ])

    import json, re
    raw = getattr(resp, "content", str(resp))
    # JSON 블록만 추출
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"grounding": 0.5, "relevance": 0.5, "reason": "파싱 실패"}


# ── 데모 파이프라인 ────────────────────────────────────────────────────────

DEMO_CASES = [
    {
        "question": "LangChain LCEL이란 무엇인가요?",
        "context": (
            "LangChain Expression Language(LCEL)는 체인을 선언적으로 구성하는 방법입니다. "
            "파이프(|) 연산자로 Runnable 객체를 연결하며 스트리밍, 배치, 비동기를 지원합니다."
        ),
        # 좋은 답변 — 컨텍스트 기반
        "good_answer": "LCEL은 LangChain에서 체인을 | 연산자로 선언적으로 구성하는 방법으로, 스트리밍과 배치를 지원합니다.",
        # 나쁜 답변 — 환각 포함
        "bad_answer": "LCEL은 LangChain의 클라우드 서비스로, GPT-5 모델에 접근하기 위한 API입니다.",
    },
]


def _run_local_evaluation():
    """Langfuse 없이 LLM-as-Judge만 실행합니다."""
    for case in DEMO_CASES:
        print(f"\n[bold]질문:[/bold] {case['question']}")

        for label, answer in [("좋은 답변", case["good_answer"]), ("나쁜 답변", case["bad_answer"])]:
            scores = _llm_judge(case["question"], case["context"], answer)
            color = "green" if scores.get("grounding", 0) > 0.7 else "red"
            print(Panel(
                f"[dim]{answer}[/dim]\n\n"
                f"grounding: [{color}]{scores.get('grounding')}[/{color}]  "
                f"relevance: {scores.get('relevance')}\n"
                f"근거: {scores.get('reason')}",
                title=label,
                border_style=color,
            ))


def _run_with_langfuse_scores(lf: "Langfuse"):
    """Trace를 생성하고 LLM-as-Judge 결과를 Score로 기록합니다."""

    @observe()
    def rag_answer(question: str, context: str) -> str:
        langfuse_context.update_current_trace(
            name="eval-demo",
            tags=["evaluation", "llm-judge"],
        )
        llm = build_chat_model(temperature=0)
        resp = llm.invoke([
            SystemMessage(content=f"컨텍스트:\n{context}\n\n컨텍스트 정보만 사용해서 답하세요."),
            HumanMessage(content=question),
        ])
        return getattr(resp, "content", str(resp))

    case = DEMO_CASES[0]
    answer = rag_answer(case["question"], case["context"])
    print(f"[bold]생성된 답변:[/bold] {answer[:150]}...")

    # LLM-as-Judge 채점
    scores = _llm_judge(case["question"], case["context"], answer)
    print(f"[bold]Judge 채점:[/bold] grounding={scores['grounding']}, relevance={scores['relevance']}")

    # 마지막 Trace에 Score 기록
    # 실제 운영에서는 trace_id를 보존해두고 비동기로 채점하는 패턴을 권장합니다
    traces = lf.fetch_traces(name="eval-demo", limit=1).data
    if traces:
        trace_id = traces[0].id
        lf.score(
            trace_id=trace_id,
            name="grounding",
            value=scores["grounding"],
            comment=scores.get("reason", ""),
        )
        lf.score(
            trace_id=trace_id,
            name="relevance",
            value=scores["relevance"],
        )
        # 사용자 피드백 시뮬레이션: 1=thumbs up, 0=thumbs down
        lf.score(
            trace_id=trace_id,
            name="user_feedback",
            value=1,
            data_type="BOOLEAN",
            comment="demo: 사용자가 좋아요를 눌렀다고 가정",
        )
        print(f"[green]✓ Score 기록 완료 (trace_id: {trace_id[:8]}...)[/green]")
    else:
        print("[yellow]Trace를 찾지 못했습니다. 잠시 후 대시보드에서 수동으로 확인하세요.[/yellow]")


# ── main ───────────────────────────────────────────────────────────────────

def main():
    header("Monitoring 04 — 답변 품질 평가 (LLM-as-Judge + 사용자 피드백)")

    print("[bold]▶ Step 1: 로컬 LLM-as-Judge 평가[/bold]")
    _run_local_evaluation()

    if not LANGFUSE_AVAILABLE:
        print("\n[yellow]langfuse 미설치 — Score 기록 단계를 건너뜁니다.[/yellow]")
        return

    if not os.getenv("LANGFUSE_SECRET_KEY"):
        print("\n[yellow]LANGFUSE_SECRET_KEY 미설정 — Score 기록 단계를 건너뜁니다.[/yellow]")
        return

    print("\n[bold]▶ Step 2: Langfuse에 Trace + Score 기록[/bold]")
    lf = Langfuse()
    _run_with_langfuse_scores(lf)
    lf.flush()

    print("\n[bold cyan]→ Langfuse 대시보드 → Traces → eval-demo → Scores 탭을 확인하세요.[/bold cyan]")
    print("[dim]  Scores 메뉴에서 grounding/relevance 분포를 대시보드로 볼 수 있습니다.[/dim]")


if __name__ == "__main__":
    main()
