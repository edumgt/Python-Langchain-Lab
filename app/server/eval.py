"""
Eval(평가) 지표 모듈

측정 지표:
  - 사용자 만족도 (User Satisfaction Score): 피드백 👍/👎 기반
  - 모드별 정확도 (Mode Accuracy): 사용자가 선택한 모드 vs 자동 라우팅 모드 일치율
  - RAG 검색 커버리지 (Coverage): 응답에 출처 문서가 포함된 비율
  - 피드백 전환율 (Feedback Rate): 전체 응답 중 피드백을 남긴 비율
"""
from __future__ import annotations

from app.server.feedback import _load


def satisfaction_score() -> dict:
    """모드별 사용자 만족도 점수 (👍비율 0~1)."""
    data = _load()
    feedbacks = data.get("feedbacks", [])
    if not feedbacks:
        return {"overall": None, "by_mode": {}}

    mode_stats: dict[str, dict] = {}
    for fb in feedbacks:
        m = fb["mode"]
        mode_stats.setdefault(m, {"up": 0, "total": 0})
        if fb["rating"] == 1:
            mode_stats[m]["up"] += 1
        mode_stats[m]["total"] += 1

    by_mode = {
        m: round(s["up"] / s["total"], 3)
        for m, s in mode_stats.items()
    }

    total_up = sum(s["up"] for s in mode_stats.values())
    total    = sum(s["total"] for s in mode_stats.values())
    overall  = round(total_up / total, 3) if total else None

    return {"overall": overall, "by_mode": by_mode}


def rag_coverage() -> dict:
    """RAG 모드 응답 중 출처 문서가 1개 이상 포함된 비율."""
    data = _load()
    feedbacks = data.get("feedbacks", [])
    rag_feedbacks = [fb for fb in feedbacks if fb["mode"] == "rag"]
    if not rag_feedbacks:
        return {"coverage": None, "total_rag": 0}

    covered = sum(1 for fb in rag_feedbacks if fb.get("used_docs"))
    return {
        "coverage": round(covered / len(rag_feedbacks), 3),
        "total_rag": len(rag_feedbacks),
        "with_sources": covered,
    }


def feedback_rate(total_responses: int) -> dict:
    """전체 응답 수 대비 피드백 제출 비율."""
    data = _load()
    feedback_count = len(data.get("feedbacks", []))
    if total_responses <= 0:
        return {"rate": None, "feedback_count": feedback_count}
    return {
        "rate": round(feedback_count / total_responses, 3),
        "feedback_count": feedback_count,
        "total_responses": total_responses,
    }


def full_report(total_responses: int = 0) -> dict:
    """모든 Eval 지표를 한 번에 반환."""
    sat  = satisfaction_score()
    cov  = rag_coverage()
    rate = feedback_rate(total_responses)

    # 종합 점수 (0~100): 만족도 60% + 커버리지 40%
    sat_val = sat["overall"] or 0
    cov_val = cov["coverage"] or 0
    composite = round((sat_val * 0.6 + cov_val * 0.4) * 100, 1)

    return {
        "composite_score": composite,
        "satisfaction": sat,
        "rag_coverage": cov,
        "feedback_rate": rate,
        "interpretation": _interpret(sat_val, cov_val),
    }


def _interpret(sat: float, cov: float) -> str:
    if sat == 0 and cov == 0:
        return "데이터 부족 — 피드백을 더 수집해야 합니다."
    if sat >= 0.8 and cov >= 0.8:
        return "우수 — 사용자 만족도와 RAG 커버리지 모두 높습니다."
    if sat >= 0.6:
        return "양호 — 만족도는 괜찮으나 RAG 출처 커버리지 개선이 필요합니다." if cov < 0.6 else "양호"
    return "개선 필요 — 프롬프트 또는 문서 인덱싱을 점검하세요."
