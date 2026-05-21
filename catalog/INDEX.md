# Catalog Index

- health: `catalog/health/00_healthcheck.py`
- prompts: `catalog/prompts/*`
- lcel: `catalog/lcel/*`
- output: `catalog/output/*`
- structured: `catalog/structured/*`
- memory: `catalog/memory/*`
- tools: `catalog/tools/*`
- agents: `catalog/agents/*`
- rag: `catalog/rag/*`
- routers: `catalog/routers/*`
- sql: `catalog/sql/*`
- callbacks: `catalog/callbacks/*`
- eval: `catalog/eval/*`

## v2 additions
- langgraph: `catalog/langgraph/*`
- guardrails: `catalog/guardrails/*`
- perf/cache: `catalog/perf/*`

## v3 additions
- rag: FAISS/BM25/Ensemble/Self-Query demos (`catalog/rag/08~11_*.py`)
- langgraph: checkpoint/subgraph/multi-role (`catalog/langgraph/04~06_*.py`)
- guardrails: citation-required (`catalog/guardrails/04_citation_required_guard.py`)
- perf: batch-vs-single (`catalog/perf/02_batch_vs_single.py`)

## v4 additions
- agents: safe tool router + validation (`catalog/agents/03_safe_tool_router.py`)
- tools: tool result validator (`catalog/tools/04_tool_result_validator.py`)
- langgraph: HITL approval pattern (`catalog/langgraph/07_hitl_approval.py`)
- eval: RAG regression runner (`catalog/eval/03_rag_regression.py`)
- data: golden set (`data/eval/golden.jsonl`)

## v5 additions
- eval: llm judge grounding (`catalog/eval/04_llm_judge_grounding.py`)
- eval: suite runner (`catalog/eval/05_eval_suite_runner.py`)
- guardrails: llm policy classifier (`catalog/guardrails/05_policy_classifier_llm.py`)
- langgraph: hitl cli pause (`catalog/langgraph/08_hitl_cli_pause.py`)

## v7 additions
- app: domain tools module (`app/tools/*`) + FastAPI endpoints (`/tools/*`)
- docs: tools api (`docs/TOOLS_API.md`)

## v8 additions
- api: doc upload/list (`/docs/*`), self-query (`/rag/self-query`), proposal generator (`/artbiz/proposal`)
- core: metadata sidecar + ingest_dir_meta (`app/core/rag_utils.py`)
- eval: tools accuracy (`catalog/eval/06_tools_accuracy.py`)

## v9 additions
- server: metadata extractor (`app/server/metadata_extractor.py`)
- server: self query parser (`app/server/self_query_parser.py`)
- api: /rag/self-query, /artbiz/proposal (+HITL approve)
- docs: v9 features and curl (`docs/V9_FEATURES.md`, `docs/curl_v9.sh`)

## v10 additions
- ops: reindex queue endpoints + worker (`/ops/*`, `catalog/ops/01_index_worker.py`)
- proposal: save MD/PDF + version list (`app/server/proposal_store.py`, `app/server/pdf_renderer.py`)
- eval: citation compliance (`catalog/eval/07_citation_compliance.py`)
- docs: v10 features + curl (`docs/V10_FEATURES.md`, `docs/curl_v10.sh`)

## v11 additions
- pdf: styled markdown renderer (`app/server/pdf_renderer.py`)
- proposal: tags/template_version/approval metadata (`app/server/proposal_store.py`)
- docs: v11 features (`docs/V11_FEATURES.md`)

## v12 additions
- pdf: publication template (cover/toc/header/footer) + theme/fonts (`app/server/pdf_renderer.py`, `pdf_theme.py`, `pdf_fonts.py`)
- assets: fonts guide (`assets/fonts/README.md`)
- docs: v12 features (`docs/V12_FEATURES.md`)

## v13 additions
- proposal: fixed template + normalizer (`app/server/proposal_template.py`, `proposal_normalizer.py`)
- api: /artbiz/proposal/template, /artbiz/proposal/check
- eval: structure compliance (`catalog/eval/08_structure_compliance.py`)
- docs: v13 features (`docs/V13_FEATURES.md`)

## v14 additions
- proposal: section rewrite + deterministic tables (`proposal_section_rewriter.py`, `proposal_table_fillers.py`)
- consistency: tool_data vs tables (`proposal_consistency.py`)
- eval: tooldata consistency (`catalog/eval/09_tooldata_consistency.py`)
- docs: v14 features (`docs/V14_FEATURES.md`)

## v15 additions
- citations: section-level footnote insertion + placement check (`proposal_citation_enforcer.py`)
- eval: citation placement (`catalog/eval/10_citation_placement.py`)
- docs: v15 features (`docs/V15_FEATURES.md`)

## v16 additions
- footnotes: SOURCE -> [1]/[2] + appendix snippet mapping (`proposal_footnotes.py`)
- eval: footnote mapping (`catalog/eval/11_footnote_mapping.py`)
- docs: v16 features (`docs/V16_FEATURES.md`)

## v17 additions
- monitoring: Langfuse LLM Observability 연동 (`catalog/monitoring/*`)
  - 01_langfuse_tracing.py     — @observe 데코레이터로 RAG 파이프라인 Trace
  - 02_langfuse_cost_tracking.py — generation span으로 토큰/비용 집계
  - 03_langfuse_prompt_management.py — 서버 프롬프트 버전 관리 및 교체
  - 04_langfuse_evaluation.py  — LLM-as-Judge Score + 사용자 피드백 기록
- lessons: Langfuse 통합 레슨 (`lessons/14_langfuse_monitoring.py`)
- settings: Langfuse 환경 변수 추가 (`app/core/settings.py`)
