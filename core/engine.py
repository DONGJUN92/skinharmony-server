"""신호등 판정 엔진 + 리포트 렌더러.

판정 규칙(높은 위험 우선):
- RED    : HIGH_RISK 플래그(규제 강화/국내 배합 불가) / 고효능 성분이 상위 인덱스(고농축 추정)
- YELLOW : EU26 착향 알레르기 / RESTRICTED(사용한도 원료) / 고효능 성분 중위 인덱스 / 민감성 자극(IRRITANT_SENSITIVE)
- GREEN  : 위 해당 없음
개인화: user_prefs의 AVOID(★)/PREFER(👍) 하이라이트.
"""
from __future__ import annotations

from .normalizer import MatchResult

MAX_RESPONSE_CHARS = 20000  # 24k 하드리밋 대비 여유
HIGH_POTENCY_TOP_INDEX = 5   # 이 인덱스 이내의 고효능 성분 = 고농축 추정(RED)
HIGH_POTENCY_MID_INDEX = 12  # 이 인덱스 이내 = 중농도 추정(YELLOW)
TREND_LABEL = "🔥트렌드"

CAT_KO = {
    "RETINOID": "레티노이드(주름개선)", "VITC": "비타민C(미백·항산화)", "AHA": "AHA 각질산",
    "BHA": "BHA 각질산", "PHA": "PHA 각질산(순한)", "NIACINAMIDE": "나이아신아마이드(미백)",
    "COPPER_PEPTIDE": "카퍼펩타이드", "PEPTIDE": "펩타이드", "BPO": "벤조일퍼옥사이드",
    "AZELAIC": "아젤라익애씨드", "REGENERATIVE": "재생(PDRN 등)", "SOOTHING": "진정",
    "BARRIER": "장벽강화", "FRAGRANCE": "착향", "PRESERVATIVE": "보존제", "UV_FILTER": "자외선차단",
    "HUMECTANT_ACTIVE": "보습 액티브", "BRIGHTENER": "미백", "ANTI_AGING": "주름개선",
}


def weight(index: int) -> float:
    """함량 순서 가중치 W = 1/(index+1). 전성분은 함량 내림차순 기재(화장품법)."""
    return 1.0 / (index + 1)


# 고효능 성분 표기 농도(%) 임계값: cat -> (주의 기준, 위험 기준)  [기획 기능 ⑦]
PCT_THRESHOLDS = {
    "RETINOID": (0.1, 0.5),
    "AHA": (5.0, 10.0),
    "BHA": (0.5, 2.0),
    "VITC": (10.0, 20.0),
    "NIACINAMIDE": (5.0, 10.0),
}


def judge(m: MatchResult) -> tuple[str, str]:
    """(등급, 사유) 반환. 등급: RED|YELLOW|GREEN"""
    ing = m.ingredient
    assert ing is not None
    if "HIGH_RISK" in ing.flags:
        return "RED", ing.note or (ing.limit or "규제 강화 추세 성분입니다.")
    # 표기 농도(%)가 있으면 인덱스 추정보다 우선 판정 [기능 ⑦: 주의/경고/위험 3단계]
    if m.pct is not None and ing.cat in PCT_THRESHOLDS:
        warn_th, danger_th = PCT_THRESHOLDS[ing.cat]
        if m.pct >= danger_th:
            return "RED", f"표기 농도 {m.pct:g}% — 고농도 구간이에요. 피부 장벽 자극 위험이 있어 저녁 소량·패치테스트 후 사용을 권장해요."
        if m.pct >= warn_th:
            return "YELLOW", f"표기 농도 {m.pct:g}% — 유효 농도 구간이에요. 처음이라면 격일 사용부터 시작하세요."
        return "GREEN", f"표기 농도 {m.pct:g}% — 순한 농도 구간이라 부담이 적어요."
    if "HIGH_POTENCY" in ing.flags and m.index < HIGH_POTENCY_TOP_INDEX:
        return "RED", f"고효능 성분이 전성분 상위({m.index + 1}번째)에 있어 고농축으로 추정됩니다. 민감성 피부는 패치테스트를 권장해요."
    if "ALLERGEN_EU26" in ing.flags:
        return "YELLOW", "EU 표시의무 착향 알레르기 유발 성분(26종)입니다. 향 알레르기가 있다면 주의하세요."
    if "ALLERGEN_GROUP" in ing.flags:
        return "YELLOW", "구체 성분이 공개되지 않는 통칭 '향료'입니다. 민감성 피부는 무향 제품이 무난해요."
    if "RESTRICTED" in ing.flags:
        return "YELLOW", ing.limit or "식약처 사용한도가 정해진 원료입니다."
    if "HIGH_POTENCY" in ing.flags and m.index < HIGH_POTENCY_MID_INDEX:
        return "YELLOW", f"고효능 성분(전성분 {m.index + 1}번째). 처음 쓴다면 저녁 소량부터 시작하세요."
    if "IRRITANT_SENSITIVE" in ing.flags:
        return "YELLOW", "민감성 피부에 자극이 될 수 있는 성분입니다."
    return "GREEN", ing.limit or "규제 이슈가 없는 성분입니다."


def _line(m: MatchResult, grade: str, reason: str, prefs: dict[str, str]) -> str:
    ing = m.ingredient
    icon = {"RED": "🔴", "YELLOW": "🟡", "GREEN": "🟢"}[grade]
    tags = []
    if prefs.get(ing.id) == "AVOID":
        tags.append("★회피 성분!")
    elif prefs.get(ing.id) == "PREFER":
        tags.append("👍선호 성분")
    if "TREND" in ing.flags:
        tags.append(TREND_LABEL)
    cat = CAT_KO.get(ing.cat)
    label = f"**{ing.ko}({ing.en})**" + (f" · {cat}" if cat else "")
    note = f" _{m.raw} → 표준명 매칭_" if m.method in ("fuzzy", "contains", "variant") else ""
    return f"- {icon} {label} {' '.join(tags)} — {reason}{note}"


def render_report(product_name: str | None, matched: list[MatchResult], unmatched: list[MatchResult],
                  prefs: dict[str, str] | None = None, skin_concern: str | None = None) -> str:
    prefs = prefs or {}
    actives = [m for m in matched if not m.ingredient.is_base]
    bases = [m for m in matched if m.ingredient.is_base]

    judged = [(m, *judge(m)) for m in actives]
    reds = [j for j in judged if j[1] == "RED"]
    yellows = [j for j in judged if j[1] == "YELLOW"]
    greens = [j for j in judged if j[1] == "GREEN"]
    # 정렬: 개인 회피 → (민감성 고민 시 자극 성분 부스트) → 트렌드 → 함량 가중치
    sensitive = bool(skin_concern) and ("민감" in skin_concern or "자극" in skin_concern or "트러블" in skin_concern)

    def _is_irritant(ing):
        return ing.cat == "FRAGRANCE" or "IRRITANT_SENSITIVE" in ing.flags or "ALLERGEN_EU26" in ing.flags or "ALLERGEN_GROUP" in ing.flags

    def sort_key(j):
        m = j[0]
        return (
            0 if prefs.get(m.ingredient.id) == "AVOID" else 1,
            0 if (sensitive and _is_irritant(m.ingredient)) else 1,
            0 if "TREND" in m.ingredient.flags else 1,
            -weight(m.index),
        )
    for group in (reds, yellows, greens):
        group.sort(key=sort_key)

    title = f"🧴 [{product_name}] 성분 리포트" if product_name else "🧴 성분 리포트"
    header = f"## {title}  (🔴{len(reds)} · 🟡{len(yellows)} · 🟢{len(greens)})"

    # 친구 톤 한 줄 결론 — 인식 실패 시 '무난' 오판 방지
    avoid_hits = [m for m, *_ in judged if prefs.get(m.ingredient.id) == "AVOID"]
    if not matched and unmatched:
        summary = "성분을 하나도 인식하지 못했어요 😥 쉼표로 구분된 전성분인지 확인하고 다시 붙여넣어 주세요. (인식 안 된 성분은 판단하지 않아요)"
    elif avoid_hits:
        summary = f"잠깐! 회원님이 피하기로 한 **{avoid_hits[0].ingredient.ko}**이(가) 들어있어요 😨 아래 확인하고 결정하세요."
    elif reds:
        summary = "몇 가지 확인이 필요한 성분이 있어요. 아래 🔴 항목부터 봐주세요!"
    elif yellows:
        summary = "한마디로: 큰 위험은 없고, 🟡 몇 가지만 체크하면 돼요 🙂"
    elif not actives and unmatched:
        summary = "인식된 성분 중 특이사항은 없지만, 미확인 성분이 있어 완전한 판단은 어려워요. 아래 목록을 확인해 주세요."
    else:
        summary = "한마디로: 규제 이슈 없는 무난한 구성이에요 👍"

    lines = [header, summary, ""]
    for m, grade, reason in (reds + yellows):
        lines.append(_line(m, grade, reason, prefs))
    # 🟢은 요약 우선(응답 크기 관리), 개인 선호·트렌드만 개별 표기
    green_notable = [j for j in greens if prefs.get(j[0].ingredient.id) == "PREFER" or "TREND" in j[0].ingredient.flags]
    for m, grade, reason in green_notable[:6]:
        lines.append(_line(m, grade, reason, prefs))
    rest_green = len(greens) - len(green_notable[:6])
    if rest_green > 0:
        lines.append(f"- 🟢 그 외 **{rest_green}개 성분**은 규제 이슈가 없어요.")
    if bases:
        lines.append(f"- ⚪ 베이스 성분 {len(bases)}개(정제수·글리세린 등)는 분석 노이즈 방지를 위해 제외했어요.")
    if unmatched:
        names = ", ".join(u.raw for u in unmatched[:8])
        lines.append(f"\n> ❓ **표준명 미확인 {len(unmatched)}건**: {names}{' 외' if len(unmatched) > 8 else ''} — 확실하지 않은 성분은 추측하지 않아요. 철자를 확인해 다시 알려주세요.")
    if sensitive:
        lines.append(f"\n> 💬 '{skin_concern}' 고민을 반영해 향료·알레르기·자극 성분을 위쪽에 배치했어요.")
    elif skin_concern:
        lines.append(f"\n> 💬 '{skin_concern}' 고민 참고했어요. 자극 관련 우선 정렬은 '민감성'이라고 알려주시면 적용돼요.")
    lines.append("")
    lines.append("💡 트러블 났던 성분이 있나요? \"OO 성분 피하고 싶어\"라고 말하면 기억해 둘게요.")
    lines.append("📤 이 결과가 유용했다면 친구에게 공유해 보세요! 다음에 화장품 살 때 또 물어봐 주세요 🙂")
    lines.append("\n> 출처: 식품의약품안전처 화장품 사용제한 원료·규제정보·기능성화장품 고시 (본 리포트는 규제·성분 정보 안내이며 의학적 진단이 아닙니다)")

    text = "\n".join(lines)
    return text[:MAX_RESPONSE_CHARS]
