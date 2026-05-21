"""Monitoring 01 — Langfuse 기본 트레이싱 (@observe)

Langfuse는 LLM 애플리케이션의 실행 흐름을 추적하는 오픈소스 Observability 플랫폼입니다.
@observe() 데코레이터를 붙이는 것만으로 함수 단위 Span이 자동 생성됩니다.

사전 준비:
  pip install langfuse openai

환경 변수 (.env):
  LANGFUSE_SECRET_KEY=sk-lf-...
  LANGFUSE_PUBLIC_KEY=pk-lf-...
  LANGFUSE_HOST=https://cloud.langfuse.com   # 또는 self-hosted URL

실행:
  docker compose run --rm lab python catalog/monitoring/01_langfuse_tracing.py
"""
from __future__ import annotations
import os
from rich import print
from app.utils.console import header
from app.core import settings
from app.core.llm_factory import build_chat_model
from langchain_core.prompts import ChatPromptTemplate

# Langfuse가 설치되지 않은 환경에서도 임포트 오류 없이 실행되도록 처리
try:
    from langfuse.decorators import observe, langfuse_context
    from langfuse import Langfuse
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False

# ── Langfuse 연결 확인 ──────────────────────────────────────────────────────

def _check_config() -> bool:
    """Langfuse 연결에 필요한 환경 변수가 모두 설정되어 있는지 확인합니다."""
    required = ["LANGFUSE_SECRET_KEY", "LANGFUSE_PUBLIC_KEY"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        print(f"[yellow]⚠ Langfuse 환경 변수 미설정: {missing}[/yellow]")
        print("[dim]  .env 파일에 LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY를 추가하세요.[/dim]")
        return False
    return True

# ── 트레이싱 대상 함수 ─────────────────────────────────────────────────────

def _retrieval_step(query: str) -> str:
    """RAG 파이프라인의 검색 단계를 흉내 냅니다."""
    # 실제 프로젝트에서는 Chroma/FAISS 검색 결과가 들어갑니다
    return f"[Mock 검색 결과] '{query}'에 관한 문서 2건"


def _generation_step(context: str, query: str) -> str:
    """LLM 호출로 최종 답변을 생성합니다."""
    llm = build_chat_model(temperature=0)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "다음 컨텍스트만 사용해서 질문에 답해줘.\n\n컨텍스트:\n{context}"),
        ("human", "{query}"),
    ])
    resp = (prompt | llm).invoke({"context": context, "query": query})
    return getattr(resp, "content", str(resp))


# ── @observe 적용 버전 ─────────────────────────────────────────────────────

def run_without_tracing(query: str) -> str:
    """트레이싱 없이 파이프라인 실행 (Langfuse 미설치 환경용)."""
    context = _retrieval_step(query)
    return _generation_step(context, query)


def _make_traced_pipeline():
    """Langfuse가 설치된 경우에만 @observe 데코레이터를 적용해 함수를 생성합니다."""
    if not LANGFUSE_AVAILABLE:
        return None

    @observe()
    def retrieval_step(query: str) -> str:
        langfuse_context.update_current_observation(
            name="retrieval",
            input={"query": query},
            metadata={"source": "mock_vector_db"},
        )
        result = _retrieval_step(query)
        langfuse_context.update_current_observation(output=result)
        return result

    @observe()
    def generation_step(context: str, query: str) -> str:
        langfuse_context.update_current_observation(
            name="llm_generation",
            input={"context": context, "query": query},
        )
        result = _generation_step(context, query)
        langfuse_context.update_current_observation(output=result)
        return result

    @observe()
    def rag_pipeline(query: str) -> str:
        """Trace 루트: 이 함수가 Langfuse에서 하나의 Trace로 표시됩니다."""
        langfuse_context.update_current_trace(
            name="rag-pipeline",
            user_id="demo-user",
            session_id="session-001",
            tags=["rag", "demo"],
        )
        context = retrieval_step(query)
        answer = generation_step(context, query)
        return answer

    return rag_pipeline


# ── main ───────────────────────────────────────────────────────────────────

def main():
    header("Monitoring 01 — Langfuse 기본 트레이싱")

    if not LANGFUSE_AVAILABLE:
        print("[yellow]langfuse 패키지가 설치되지 않았습니다.[/yellow]")
        print("[dim]  pip install langfuse 후 재실행하세요.[/dim]\n")
        print("[bold]Langfuse 없이 파이프라인 실행 (트레이싱 미적용):[/bold]")
        query = "LangChain LCEL이 무엇인지 알려줘."
        answer = run_without_tracing(query)
        print(f"[green]답변:[/green] {answer[:200]}...")
        return

    if not _check_config():
        print("\n[bold]Langfuse 없이 파이프라인 실행 (트레이싱 미적용):[/bold]")
        query = "LangChain LCEL이 무엇인지 알려줘."
        answer = run_without_tracing(query)
        print(f"[green]답변:[/green] {answer[:200]}...")
        return

    # Langfuse 클라이언트 초기화 확인
    lf = Langfuse()
    print("[green]✓ Langfuse 연결 확인됨[/green]")
    print(f"[dim]  Host: {os.getenv('LANGFUSE_HOST', 'https://cloud.langfuse.com')}[/dim]\n")

    rag_pipeline = _make_traced_pipeline()

    print("[bold]트레이싱 포함 파이프라인 실행:[/bold]")
    query = "LangChain LCEL이 무엇인지 알려줘."
    answer = rag_pipeline(query)

    # 모든 이벤트가 서버에 전송되도록 플러시
    lf.flush()

    print(f"\n[green]답변:[/green] {answer[:300]}...")
    print("\n[bold cyan]→ Langfuse 대시보드에서 Trace를 확인하세요.[/bold cyan]")
    print("[dim]  https://cloud.langfuse.com → Traces 탭[/dim]")


if __name__ == "__main__":
    main()
