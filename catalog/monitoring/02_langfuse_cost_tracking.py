"""Monitoring 02 — Langfuse 토큰/비용 추적

Langfuse는 각 LLM 호출의 입력/출력 토큰 수와 그에 따른 비용을 자동으로 집계합니다.
- OpenAI 모델은 토큰 수가 응답에 포함되어 자동 파싱됩니다.
- usage 객체를 직접 주입해 커스텀 모델 비용도 추적할 수 있습니다.

실행:
  docker compose run --rm lab python catalog/monitoring/02_langfuse_cost_tracking.py
"""
from __future__ import annotations
import os, time
from rich import print
from rich.table import Table
from app.utils.console import header
from app.core.llm_factory import build_chat_model
from langchain_core.messages import HumanMessage

try:
    from langfuse import Langfuse
    from langfuse.decorators import observe, langfuse_context
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False


PROMPTS = [
    "GPT-4o와 GPT-4o-mini의 차이를 한 문장으로 설명해줘.",
    "LangChain과 LlamaIndex의 주요 차이점을 세 가지로 정리해줘.",
    "RAG 파이프라인에서 청크 크기가 검색 품질에 미치는 영향을 설명해줘.",
]


def _run_and_measure_local(prompts: list[str]) -> list[dict]:
    """Langfuse 없이 실행하면서 응답 메타데이터(토큰 수)를 수집합니다."""
    llm = build_chat_model(temperature=0)
    results = []
    for p in prompts:
        t0 = time.time()
        resp = llm.invoke([HumanMessage(content=p)])
        elapsed = time.time() - t0

        # LangChain의 AIMessage에는 usage_metadata가 포함될 수 있습니다
        usage = getattr(resp, "usage_metadata", None) or {}
        results.append({
            "prompt": p[:50] + "...",
            "input_tokens": usage.get("input_tokens", "N/A"),
            "output_tokens": usage.get("output_tokens", "N/A"),
            "elapsed_s": round(elapsed, 2),
        })
    return results


def _display_local_table(results: list[dict]):
    table = Table(title="로컬 토큰 사용량 측정 결과")
    table.add_column("프롬프트", style="cyan", max_width=40)
    table.add_column("입력 토큰", justify="right")
    table.add_column("출력 토큰", justify="right")
    table.add_column("소요 시간", justify="right")
    for r in results:
        table.add_row(r["prompt"], str(r["input_tokens"]), str(r["output_tokens"]), f"{r['elapsed_s']}s")
    print(table)


# ── Langfuse generation span 직접 생성 ────────────────────────────────────

def _run_with_langfuse_generation(lf: "Langfuse", prompts: list[str]):
    """Langfuse의 generation span을 수동으로 생성해 토큰/비용을 기록합니다.

    - observe 데코레이터가 아닌 SDK Low-level API를 사용하는 방식입니다.
    - 커스텀 모델이나 non-OpenAI 공급자에서 유용합니다.
    """
    llm = build_chat_model(temperature=0)

    trace = lf.trace(
        name="cost-tracking-demo",
        user_id="demo-user",
        tags=["cost", "demo"],
    )

    results = []
    for i, p in enumerate(prompts):
        t0 = time.time()
        resp = llm.invoke([HumanMessage(content=p)])
        elapsed = time.time() - t0

        usage = getattr(resp, "usage_metadata", None) or {}
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        # Langfuse generation span 기록
        trace.generation(
            name=f"llm-call-{i+1}",
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            input=[{"role": "user", "content": p}],
            output=getattr(resp, "content", str(resp)),
            usage={
                "input": input_tokens,
                "output": output_tokens,
                "unit": "TOKENS",
            },
            metadata={"elapsed_s": round(elapsed, 2)},
        )

        results.append({
            "prompt": p[:50] + "...",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "elapsed_s": round(elapsed, 2),
        })

    return results


# ── main ───────────────────────────────────────────────────────────────────

def main():
    header("Monitoring 02 — 토큰/비용 추적")

    print("[bold]▶ Step 1: 로컬 토큰 사용량 측정[/bold]")
    results = _run_and_measure_local(PROMPTS)
    _display_local_table(results)

    if not LANGFUSE_AVAILABLE:
        print("\n[yellow]langfuse 미설치 — Langfuse 기록 단계를 건너뜁니다.[/yellow]")
        print("[dim]  pip install langfuse 후 재실행하면 대시보드에서 비용을 확인할 수 있습니다.[/dim]")
        return

    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    if not secret_key or not public_key:
        print("\n[yellow]LANGFUSE_SECRET_KEY / LANGFUSE_PUBLIC_KEY 미설정 — 건너뜁니다.[/yellow]")
        return

    print("\n[bold]▶ Step 2: Langfuse generation span 기록[/bold]")
    lf = Langfuse()
    traced_results = _run_with_langfuse_generation(lf, PROMPTS)
    _display_local_table(traced_results)
    lf.flush()

    print("\n[bold cyan]→ Langfuse 대시보드 → Traces → cost-tracking-demo 에서 비용을 확인하세요.[/bold cyan]")
    print("[dim]  모델별 토큰 단가가 등록되어 있으면 USD 환산 비용도 표시됩니다.[/dim]")


if __name__ == "__main__":
    main()
