"""Monitoring 03 — Langfuse 프롬프트 버전 관리

Langfuse Prompt Management를 사용하면:
- 프롬프트를 코드 밖에서 버전별로 중앙 관리
- 코드 재배포 없이 프롬프트를 교체하고 A/B 테스트
- 어떤 버전의 프롬프트가 어떤 Trace에서 사용됐는지 연결 추적

대시보드에서 프롬프트 등록:
  Langfuse → Prompts → + New Prompt
  Name: "rag-system-prompt"
  Type: text
  Content:
    당신은 {{domain}} 분야의 전문 어시스턴트입니다.
    제공된 컨텍스트 정보만 사용해서 질문에 답하세요.
    컨텍스트에 없는 정보는 "모른다"고 답하세요.

실행:
  docker compose run --rm lab python catalog/monitoring/03_langfuse_prompt_management.py
"""
from __future__ import annotations
import os
from rich import print
from app.utils.console import header
from app.core.llm_factory import build_chat_model
from langchain_core.prompts import ChatPromptTemplate

try:
    from langfuse import Langfuse
    from langfuse.decorators import observe, langfuse_context
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False


# 로컬 폴백 프롬프트 (Langfuse 미연결 시 사용)
FALLBACK_SYSTEM_PROMPT = (
    "당신은 {domain} 분야의 전문 어시스턴트입니다.\n"
    "제공된 컨텍스트 정보만 사용해서 질문에 답하세요.\n"
    "컨텍스트에 없는 정보는 '모른다'고 답하세요."
)

DEMO_CONTEXT = (
    "LangChain은 LLM 애플리케이션을 구축하기 위한 오픈소스 프레임워크입니다. "
    "LCEL(LangChain Expression Language)을 통해 체인을 선언적으로 구성할 수 있으며, "
    "Runnable 인터페이스로 스트리밍, 배치, 비동기 실행을 지원합니다."
)


def _run_with_local_prompt(query: str, domain: str) -> str:
    """로컬 폴백 프롬프트로 LLM을 실행합니다."""
    llm = build_chat_model(temperature=0)
    prompt = ChatPromptTemplate.from_messages([
        ("system", FALLBACK_SYSTEM_PROMPT),
        ("human", "컨텍스트:\n{context}\n\n질문: {query}"),
    ])
    resp = (prompt | llm).invoke({"domain": domain, "context": DEMO_CONTEXT, "query": query})
    return getattr(resp, "content", str(resp))


def _run_with_langfuse_prompt(lf: "Langfuse", prompt_name: str, query: str, domain: str) -> str:
    """Langfuse에서 프롬프트를 가져와 LLM을 실행합니다.

    - get_prompt()는 가장 최신(production) 버전을 반환합니다.
    - version=2 처럼 특정 버전을 고정할 수도 있습니다.
    - 프롬프트 객체는 내부적으로 캐싱되어 매번 서버 요청을 보내지 않습니다.
    """
    try:
        lf_prompt = lf.get_prompt(prompt_name)
    except Exception as e:
        print(f"[yellow]프롬프트 '{prompt_name}' 로드 실패: {e}[/yellow]")
        print("[dim]  대시보드에서 프롬프트를 먼저 등록해주세요. 로컬 폴백으로 실행합니다.[/dim]")
        return _run_with_local_prompt(query, domain)

    # Langfuse 프롬프트의 변수를 채워서 문자열로 컴파일
    compiled_system = lf_prompt.compile(domain=domain)

    llm = build_chat_model(temperature=0)

    # @observe와 함께 사용할 때 어떤 프롬프트 버전이 사용됐는지 자동 연결됩니다
    @observe()
    def call_llm(system: str, context: str, user_query: str) -> str:
        langfuse_context.update_current_observation(
            prompt=lf_prompt,  # 프롬프트 버전을 Trace에 연결
        )
        prompt_tmpl = ChatPromptTemplate.from_messages([
            ("system", system),
            ("human", "컨텍스트:\n{context}\n\n질문: {query}"),
        ])
        resp = (prompt_tmpl | llm).invoke({"context": context, "query": user_query})
        return getattr(resp, "content", str(resp))

    return call_llm(compiled_system, DEMO_CONTEXT, query)


# ── main ───────────────────────────────────────────────────────────────────

def main():
    header("Monitoring 03 — Langfuse 프롬프트 버전 관리")

    query = "LangChain LCEL의 주요 특징을 알려줘."
    domain = "소프트웨어 개발"

    # ── 로컬 폴백 실행 ────────────────────────────────────────────────────
    print("[bold]▶ Step 1: 로컬 폴백 프롬프트로 실행[/bold]")
    answer_local = _run_with_local_prompt(query, domain)
    print(f"[green]답변:[/green] {answer_local[:200]}...\n")

    if not LANGFUSE_AVAILABLE:
        print("[yellow]langfuse 미설치 — Langfuse 프롬프트 관리 단계를 건너뜁니다.[/yellow]")
        _print_prompt_guide()
        return

    if not os.getenv("LANGFUSE_SECRET_KEY"):
        print("[yellow]LANGFUSE_SECRET_KEY 미설정 — Langfuse 단계를 건너뜁니다.[/yellow]")
        _print_prompt_guide()
        return

    # ── Langfuse 프롬프트 실행 ─────────────────────────────────────────────
    print("[bold]▶ Step 2: Langfuse에서 프롬프트를 가져와 실행[/bold]")
    lf = Langfuse()
    answer_lf = _run_with_langfuse_prompt(lf, "rag-system-prompt", query, domain)
    lf.flush()

    print(f"[green]답변:[/green] {answer_lf[:200]}...")
    print("\n[bold cyan]→ Langfuse 대시보드 → Prompts에서 버전별 사용 횟수를 확인하세요.[/bold cyan]")


def _print_prompt_guide():
    print("\n[bold]Langfuse 프롬프트 등록 방법:[/bold]")
    print("  1. Langfuse 대시보드 → Prompts → + New Prompt")
    print("  2. Name: [cyan]rag-system-prompt[/cyan]")
    print("  3. Type: [cyan]text[/cyan]")
    print("  4. Content (변수는 {{중괄호}} 두 개 사용):")
    print("     [dim]당신은 {{domain}} 분야의 전문 어시스턴트입니다.[/dim]")
    print("     [dim]제공된 컨텍스트 정보만 사용해서 질문에 답하세요.[/dim]")
    print("  5. Save → Promote to Production")


if __name__ == "__main__":
    main()
