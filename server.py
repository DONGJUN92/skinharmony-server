"""SkinHarmony(스킨하모니) MCP 서버.

"화해가 아니라, 카톡에서 사기 직전에 물어보는 성분 친구."
- Streamable HTTP · Stateless(no session) · TextContent(마크다운) 응답
- 데이터 출처: 식약처 공공데이터(사용제한 원료·규제정보·기능성 고시) 기반 자체 사전 + 출처 명시 룰셋
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from core.compat import CompatEngine
from core.engine import render_report
from core.normalizer import Normalizer
from core.store import PrefStore

DATA_DIR = Path(__file__).resolve().parent / "data"

mcp = FastMCP(
    "SkinHarmony",
    instructions=(
        "SkinHarmony(스킨하모니) is a friendly cosmetics-ingredient consultant. "
        "Paste a full ingredient list for a traffic-light safety report, "
        "check layering compatibility between products, and remember the user's avoid/prefer ingredients. "
        "When the user mentions a trouble ingredient, call remember_ingredient. "
        "For personalization, ask the user once for a short nickname and reuse it as user_key."
    ),
    stateless_http=True,
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8000")),
)

_norm = Normalizer()
_compat = CompatEngine(_norm)
_store = PrefStore()
_demo = json.loads((DATA_DIR / "demo_sample.json").read_text(encoding="utf-8"))

RO = dict(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True)

# LLM이 한국어/자연어로 preference를 넘기는 실전 케이스 방어
_AVOID_WORDS = ("AVOID", "회피", "피하", "싫", "안맞", "안 맞", "트러블", "블랙", "나쁨", "BAD", "NEGATIVE")
_PREFER_WORDS = ("PREFER", "선호", "좋", "잘맞", "잘 맞", "맞아", "화이트", "GOOD", "POSITIVE", "LIKE")


def _coerce_preference(pref) -> str:
    p = str(pref or "").strip().upper()
    if any(w.upper() in p for w in _AVOID_WORDS):
        return "AVOID"
    if any(w.upper() in p for w in _PREFER_WORDS):
        return "PREFER"
    return p


def _coerce_products(products) -> list[dict]:
    """LLM 비정형 입력 방어: 단일 dict → 리스트, name/product_name 키 혼용 허용."""
    if isinstance(products, dict):
        products = [products]
    out = []
    for p in products or []:
        if isinstance(p, dict):
            out.append({"name": p.get("name") or p.get("product_name"),
                        "ingredients": p.get("ingredients") or p.get("ingredient_list") or []})
    return out


@mcp.tool(
    annotations=ToolAnnotations(title="성분 신호등 분석", **RO),
)
def analyze_ingredients(
    ingredients: list[str] | str | None = None,
    product_name: str | None = None,
    skin_concern: str | None = None,
    user_key: str | None = None,
    demo: bool = False,
) -> str:
    """[스킨하모니 · 화장품 성분 신호등] SkinHarmony analyzes a pasted cosmetic full-ingredient list and returns an instant traffic-light(🟢🟡🔴) safety report, based on Korean MFDS(식약처) public regulation data: restricted/limited ingredients, EU-26 fragrance allergens, and high-potency actives estimated by ingredient order. Trending ingredients (retinal, PDRN, niacinamide) are surfaced first. Pass user_key (user's nickname) to highlight personally remembered avoid/prefer ingredients. Set demo=true to show a sample report without any input — great for a first try ("예시로 보여줘"). Text input only.

    Args:
        ingredients: 전성분 리스트(함량 내림차순). demo=true면 생략 가능
        product_name: 제품명(선택, 리포트 제목)
        skin_concern: 피부 고민(선택, 예: 민감성)
        user_key: 사용자 닉네임(선택, 개인 회피/선호 성분 강조)
        demo: true면 내장 샘플로 시연 리포트 출력
    """
    if demo or not ingredients:
        if not demo and not ingredients:
            return "전성분 리스트를 쉼표로 구분해 붙여넣어 주세요! 먼저 구경만 하고 싶다면 \"예시로 보여줘\"라고 해도 돼요 🙂"
        ingredients = _demo["ingredients"]
        product_name = product_name or _demo["product_name"]
    matched, unmatched = _norm.match_list(ingredients)
    prefs = _store.get_prefs(user_key) if user_key else {}
    report = render_report(product_name, matched, unmatched, prefs, skin_concern)
    if demo:
        report = "🎬 **데모 리포트예요!** 실제 제품 전성분을 붙여넣으면 이렇게 분석해 드려요.\n\n" + report
    return report


@mcp.tool(
    annotations=ToolAnnotations(title="성분 궁합 검사 (대표 기능)", **RO),
)
def check_compatibility(products: list[dict] | dict, user_key: str | None = None) -> str:
    """[스킨하모니 · 화장품 성분 신호등] SkinHarmony's signature tool cross-checks two or more products' ingredient lists for known layering conflicts — e.g., "레티놀 크림이랑 비타민C 세럼 같이 써도 돼?" — such as Retinoid×AHA/BHA, Vitamin C×Copper Peptide, and returns a Day/Night usage routine plus synergy pairs. Conflict rules are curated with cited sources (MFDS notices, dermatology guides); unknown combinations are reported honestly, never guessed. Text input only.

    Args:
        products: 비교할 제품 목록. 각 항목은 {"name": 제품명(선택), "ingredients": [전성분]}
        user_key: 사용자 닉네임(선택)
    """
    products = _coerce_products(products)
    if not products:
        d = _demo["compat_demo"]["products"]
        return _compat.check(d) + "\n\n🎬 위는 데모예요! 실제 두 제품의 전성분을 알려주시면 진짜 궁합을 봐드려요."
    return _compat.check(products)


@mcp.tool(
    annotations=ToolAnnotations(title="성분 기억 저장", readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True),
)
def remember_ingredient(
    ingredient: str,
    preference: str,
    user_key: str,
    reason: str | None = None,
) -> str:
    """[스킨하모니 · 화장품 성분 신호등] SkinHarmony saves an ingredient to the user's personal AVOID(트러블) or PREFER(잘 맞음) list, so every future report highlights it (★avoid / 👍prefer). Ask the user for a short nickname once and pass it as user_key. Idempotent: saving the same ingredient again just updates it.

    Args:
        ingredient: 성분명(표준명/이명 허용, 예: 리모넨)
        preference: "AVOID"(회피) 또는 "PREFER"(선호)
        user_key: 사용자 닉네임(필수, 개인 구분용)
        reason: 메모(선택, 예: 붉어짐)
    """
    preference = _coerce_preference(preference)
    if preference not in ("AVOID", "PREFER"):
        return "preference는 AVOID(피하고 싶어요) 또는 PREFER(잘 맞아요) 중 하나로 알려주세요!"
    if not (user_key or "").strip():
        return "개인 기억을 위해 짧은 닉네임 하나만 알려주세요! (예: 준이) 다음부터 그 이름으로 회피/선호 성분을 기억할게요."
    m = _norm.match_one(ingredient)
    if m.matched:
        cid, display = m.ingredient.id, m.ingredient.ko
        note = "" if m.method == "exact" else f" ('{ingredient}' → 표준명 '{display}'로 저장)"
    else:
        cid, display, note = f"raw:{ingredient.strip()}", ingredient.strip(), " (표준명 미확인 — 입력한 이름 그대로 기억할게요)"
    ok = _store.save(user_key, cid, display, preference, reason)
    if not ok:
        return "닉네임에 사용할 수 없는 문자가 있어요. 한글/영문/숫자로 다시 알려주세요!"
    label = "회피(★)" if preference == "AVOID" else "선호(👍)"
    saved = _store.list_prefs(user_key)
    return (
        f"✅ **{display}**을(를) {label} 성분으로 기억했어요{note}"
        + (f" — 사유: {reason}" if reason else "")
        + f"\n앞으로 '{user_key}'님의 모든 성분 리포트에서 자동으로 강조해 드릴게요."
        + f"\n📒 현재 기억 중인 성분: {len(saved)}개"
    )


@mcp.tool(
    annotations=ToolAnnotations(title="공식 성분 정보 조회", readOnlyHint=True, destructiveHint=False, openWorldHint=True, idempotentHint=True),
)
def search_cosmetic_info(query_name: str, user_key: str | None = None) -> str:
    """[스킨하모니 · 화장품 성분 신호등] SkinHarmony looks up a single cosmetic ingredient in its standard dictionary built from Korean MFDS(식약처) public data: standard Korean/English name, category, usage limits, and regulation flags. Also shows the user's saved preference for it if user_key is given. Returns "not found" honestly when there is no match — never fabricates data.

    Args:
        query_name: 조회할 성분명(예: 페녹시에탄올, retinol)
        user_key: 사용자 닉네임(선택)
    """
    m = _norm.match_one(query_name)
    if not m.matched:
        return (
            f"'{query_name}'은(는) 표준 성분 사전에서 찾지 못했어요 🙏 (추측해서 알려드리지 않아요)\n"
            "- 철자를 확인하거나 한글 표준명/영문명(INCI)으로 다시 검색해 보세요.\n"
            "- 제품 전체가 궁금하면 전성분을 통째로 붙여넣어 주세요!"
        )
    ing = m.ingredient
    from core.engine import CAT_KO
    lines = [f"## 🔎 {ing.ko} ({ing.en})"]
    if CAT_KO.get(ing.cat):
        lines.append(f"- 분류: {CAT_KO[ing.cat]}")
    if "TREND" in ing.flags:
        lines.append("- 🔥 2026 트렌드 성분이에요!")
    if ing.limit:
        lines.append(f"- 📏 규제/고시: {ing.limit}")
    if ing.note:
        lines.append(f"- ⚠️ {ing.note}")
    if "ALLERGEN_EU26" in ing.flags:
        lines.append("- 🟡 EU 표시의무 착향 알레르기 유발 성분(26종)")
    if "BASE" in ing.flags:
        lines.append("- ⚪ 대부분 화장품에 쓰이는 베이스 성분(분석 시 노이즈로 제외)")
    if user_key:
        pref = _store.get_prefs(user_key).get(ing.id)
        if pref:
            lines.append(f"- {'★ 회원님의 회피 성분이에요!' if pref == 'AVOID' else '👍 회원님의 선호 성분이에요!'}")
    if m.method != "exact":
        lines.append(f"\n_('{query_name}' → 표준명 매칭)_")
    lines.append("\n> 출처: 식품의약품안전처 화장품 원료성분·사용제한 원료·기능성화장품 고시")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
