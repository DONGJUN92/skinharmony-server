"""궁합·충돌 검사 엔진(대표 히어로 기능).

카테고리 단위 룰 매칭: 성분쌍이 아닌 카테고리쌍으로 검사하므로
사전에 성분이 추가되면 룰 커버리지가 자동 확장된다.
룰 밖 조합은 '확인 불가'로 정직하게 처리(안전 단정 금지).
"""
from __future__ import annotations

import json
from pathlib import Path

from .engine import MAX_RESPONSE_CHARS
from .normalizer import MatchResult, Normalizer

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEV_ICON = {"WARN": "⚠️", "CAUTION": "🟡", "INFO": "ℹ️"}
SEV_ORDER = {"WARN": 0, "CAUTION": 1, "INFO": 2}


class CompatEngine:
    def __init__(self, normalizer: Normalizer, data_path: Path | None = None):
        raw = json.loads((data_path or DATA_DIR / "conflict_rules.json").read_text(encoding="utf-8"))
        self.rules = raw["rules"]
        self.synergies = raw.get("synergies", [])
        self.norm = normalizer

    @staticmethod
    def _profile(matched: list[MatchResult]) -> dict[str, list[MatchResult]]:
        """제품의 카테고리/플래그 프로파일: key -> 해당 성분들"""
        prof: dict[str, list[MatchResult]] = {}
        for m in matched:
            prof.setdefault(m.ingredient.cat, []).append(m)
            for f in m.ingredient.flags:
                prof.setdefault(f, []).append(m)
        return prof

    def check(self, products: list[dict]) -> str:
        if len(products) < 2:
            return "두 제품 이상의 전성분을 알려주시면 궁합을 비교해 드려요! (예: A 제품 성분 ..., B 제품 성분 ...)"

        parsed = []
        for i, p in enumerate(products):
            name = p.get("name") or f"제품 {chr(65 + i)}"
            matched, unmatched = self.norm.match_list(p.get("ingredients", []))
            parsed.append({"name": name, "matched": matched, "unmatched": unmatched,
                           "profile": self._profile(matched)})

        conflicts, infos, synergy_hits = [], [], []
        for a in range(len(parsed)):
            for b in range(a + 1, len(parsed)):
                pa, pb = parsed[a], parsed[b]
                for rule in self.rules:
                    k1, k2 = rule["pair"]
                    for x, y in ((k1, k2), (k2, k1)):
                        if x in pa["profile"] and y in pb["profile"]:
                            hit = {
                                "rule": rule, "a": pa["name"], "b": pb["name"],
                                "ing_a": pa["profile"][x][0].ingredient.ko,
                                "ing_b": pb["profile"][y][0].ingredient.ko,
                            }
                            (infos if rule["severity"] == "INFO" else conflicts).append(hit)
                            break
                for syn in self.synergies:
                    k1, k2 = syn["pair"]
                    for x, y in ((k1, k2), (k2, k1)):
                        if x in pa["profile"] and y in pb["profile"]:
                            synergy_hits.append({"syn": syn, "a": pa["name"], "b": pb["name"],
                                                 "ing_a": pa["profile"][x][0].ingredient.ko,
                                                 "ing_b": pb["profile"][y][0].ingredient.ko})
                            break

        conflicts.sort(key=lambda h: SEV_ORDER[h["rule"]["severity"]])
        names = " × ".join(p["name"] for p in parsed)
        lines = [f"## 🤝 [{names}] 궁합 리포트"]

        if conflicts:
            lines.append(f"결론부터: **같이 바르는 건 비추!** 시간대를 나누면 둘 다 잘 쓸 수 있어요 🙂\n")
            lines.append(f"### ⚠️ 주의할 조합 {len(conflicts)}건")
            for h in conflicts[:8]:
                r = h["rule"]
                lines.append(f"- {SEV_ICON[r['severity']]} **{h['ing_a']}**({h['a']}) × **{h['ing_b']}**({h['b']}): {r['reason']}")
                if r.get("routine"):
                    lines.append(f"  - ☀️ 아침: {r['routine']['day']} / 🌙 저녁: {r['routine']['night']}")
        else:
            lines.append("결론부터: 알려진 충돌 규칙에는 걸리는 게 없어요 👍 (단, 모든 조합을 보장하는 건 아니에요)")

        for h in infos[:3]:
            lines.append(f"- ℹ️ {h['ing_a']} × {h['ing_b']}: {h['rule']['reason']}")

        # 스키니멀리즘: 구성이 거의 같은 제품 안내(중복 구매 방지)
        for a in range(len(parsed)):
            for b in range(a + 1, len(parsed)):
                ids_a = {m.ingredient.id for m in parsed[a]["matched"]}
                ids_b = {m.ingredient.id for m in parsed[b]["matched"]}
                if len(ids_a) >= 3 and len(ids_b) >= 3:
                    jaccard = len(ids_a & ids_b) / len(ids_a | ids_b)
                    if jaccard >= 0.7:
                        lines.append(f"\n💸 **{parsed[a]['name']}**와 **{parsed[b]['name']}**는 인식된 성분 구성이 {jaccard:.0%} 겹쳐요. 사실상 비슷한 제품이라 둘 중 하나면 충분할 수 있어요! (스마트 스키니멀리즘)")
        if synergy_hits:
            lines.append(f"\n### 💚 시너지 조합")
            for h in synergy_hits[:3]:
                lines.append(f"- {h['ing_a']} × {h['ing_b']}: {h['syn']['reason']}")

        un_total = sum(len(p["unmatched"]) for p in parsed)
        if un_total:
            lines.append(f"\n> ❓ 표준명 미확인 성분 {un_total}건은 궁합 판정에서 제외했어요(추측 금지 원칙).")
        lines.append("\n📤 이 궁합 결과, 같은 제품 쓰는 친구에게 공유해 보세요!")
        lines.append("> 근거: 자체 구축 성분 상호작용 룰셋(식약처 고시·피부과 임상 가이드 기반, 각 항목 출처 표기) — 의학적 진단이 아닌 일반 성분 정보입니다.")
        return "\n".join(lines)[:MAX_RESPONSE_CHARS]
