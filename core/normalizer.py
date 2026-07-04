"""성분명 정규화 엔진.

정확도 전략(우선순위 순):
1) 정확 매칭 — 표준명(ko/en)·이명(alias) 사전
2) 퍼지 매칭 — difflib 유사도(기본 임계 0.87). 오탈자·띄어쓰기 변형 흡수
3) 부분 매칭 — 액티브 성분 한정(예: '레티놀리포좀' → 레티놀). 오탐 방지 위해 화이트리스트 카테고리만
4) 미확인 — 절대 추정하지 않고 unmatched로 분리 반환
"""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FUZZY_THRESHOLD = 0.87
# 부분 매칭을 허용하는 액티브 카테고리(베이스 성분은 부분 매칭 금지 → 오탐 방지)
CONTAINMENT_CATS = {"RETINOID", "VITC", "AHA", "BHA", "PHA", "NIACINAMIDE", "COPPER_PEPTIDE", "BPO", "AZELAIC", "REGENERATIVE"}

_PUNCT_RE = re.compile(r"[\s\-·,./()\[\]{}'\"‘’“”]+")
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_PAREN_RE = re.compile(r"\(([^)]*)\)")


# 한글 INCI 구명칭 → 협회(대한화장품협회) 표준명 정규화 규칙.
# 대한화장품협회 성분사전 표준화 기준(2008~) 기반: 영어 발음식 표기로 통일.
#   이소→아이소, 메칠→메틸, 디올→다이올, 나트륨→소듐, 칼륨→포타슘, 히드록시→하이드록시 등.
# 규칙 하나가 성분 클래스 전체를 커버 → 개별 별칭보다 확장성이 높다.
# canonical 방향 = 표준명(신명칭). 표준명은 대부분 자기 자신으로 접혀 무손실(자기일관성 테스트로 검증).
_FOLD_RULES = [
    # 금속염 구명칭
    ("나트륨", "소듐"),
    ("칼륨", "포타슘"),
    # 접두/어간
    ("히드록시", "하이드록시"),
    ("카르복시", "카복시"),
    ("메칠", "메틸"), ("에칠", "에틸"), ("부칠", "부틸"), ("옥칠", "옥틸"), ("세칠", "세틸"),
    ("치아졸", "티아졸"),
    ("메치콘", "메티콘"),
    # di- 계열(디→다이)은 오탐 방지를 위해 대표 어간만 타깃팅
    ("디메티콘", "다이메티콘"), ("디소듐", "다이소듐"), ("디포타슘", "다이포타슘"),
    ("디프로필렌", "다이프로필렌"), ("디올", "다이올"),
    # -glycol / -siloxane / oxide / sorbitan / shea
    ("글리콜", "글라이콜"),
    ("실록산", "실록세인"),
    ("옥시드", "옥사이드"),
    ("솔비탄", "소르비탄"),
    ("쉐어", "시어"),
]
# 'iso→아이소'는 이미 '아이소'인 경우를 건드리지 않도록 lookbehind 정규식 사용
_FOLD_RE = [(re.compile(r"(?<!아)이소"), "아이소")]


def _fold(key: str) -> str:
    """정규화된 키를 협회 표준명 기준 canonical 형태로 접는다."""
    for a, b in _FOLD_RULES:
        key = key.replace(a, b)
    for rx, b in _FOLD_RE:
        key = rx.sub(b, key)
    return key


def _name_candidates(s: str) -> list[str]:
    """'리모넨(Limonene)' → ['리모넨(Limonene)', '리모넨', 'Limonene'].
    한/영 병기·부연 괄호를 각각 독립 후보로 분리해 매칭 성공률을 높인다."""
    s = (s or "").strip()
    cands = [s]
    if "(" in s:
        before = s.split("(", 1)[0].strip()
        if before:
            cands.append(before)
        for inside in _PAREN_RE.findall(s):
            inside = inside.strip()
            if inside:
                cands.append(inside)
    return cands


def _norm_key(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").strip().lower()
    return _PUNCT_RE.sub("", s)


def extract_pct(raw: str) -> tuple[str, float | None]:
    """'나이아신아마이드 5%' → ('나이아신아마이드', 5.0). 표기 농도는 판정에서 인덱스 추정보다 우선."""
    m = _PCT_RE.search(raw or "")
    if not m:
        return raw, None
    return _PCT_RE.sub("", raw).strip(), float(m.group(1))


@dataclass
class Ingredient:
    id: str
    ko: str
    en: str
    cat: str
    flags: list[str] = field(default_factory=list)
    limit: str | None = None
    note: str | None = None

    @property
    def is_base(self) -> bool:
        return "BASE" in self.flags


@dataclass
class MatchResult:
    raw: str            # 사용자가 입력한 원문
    index: int          # 전성분표 내 순서(함량 가중치용)
    ingredient: Ingredient | None
    method: str         # exact | fuzzy | contains | none
    score: float = 1.0
    pct: float | None = None  # 표기 농도(예: '레티놀 0.1%' → 0.1). 있으면 인덱스 추정보다 우선

    @property
    def matched(self) -> bool:
        return self.ingredient is not None


class Normalizer:
    def __init__(self, data_path: Path | None = None):
        raw = json.loads((data_path or DATA_DIR / "ingredients.json").read_text(encoding="utf-8"))
        self.ingredients: dict[str, Ingredient] = {}
        self._lookup: dict[str, str] = {}  # norm_key -> ingredient id
        for item in raw["ingredients"]:
            ing = Ingredient(
                id=item["id"], ko=item["ko"], en=item["en"], cat=item["cat"],
                flags=item.get("flags", []), limit=item.get("limit"), note=item.get("note"),
            )
            self.ingredients[ing.id] = ing
            for name in [ing.ko, ing.en, *item.get("alias", [])]:
                key = _norm_key(name)
                if key:
                    self._lookup.setdefault(key, ing.id)
        self._keys = list(self._lookup.keys())
        # 표기 변형 대응: 접힌(folded) 키 → id. 실록세인/실록산, 시어/쉐어 등 클래스 단위 흡수
        self._folded_lookup: dict[str, str] = {}
        for key, ing_id in self._lookup.items():
            self._folded_lookup.setdefault(_fold(key), ing_id)
        # 부분 매칭 후보: 액티브 카테고리의 한글 표준명(3글자 이상만 — 짧은 키 오탐 방지)
        self._contain_keys = [
            (_norm_key(ing.ko), ing.id) for ing in self.ingredients.values()
            if ing.cat in CONTAINMENT_CATS and len(_norm_key(ing.ko)) >= 3
        ]

    def match_one(self, raw: str, index: int = 0) -> MatchResult:
        clean, pct = extract_pct(raw)  # '레티놀 0.1%' → 이름/농도 분리
        # 한/영 병기 '리모넨(Limonene)' 대응: 전체·괄호앞·괄호안을 각각 후보로 시도
        cand_keys = []
        for c in _name_candidates(clean):
            k = _norm_key(c)
            if k and k not in cand_keys:
                cand_keys.append(k)
        if not cand_keys:
            return MatchResult(raw=raw, index=index, ingredient=None, method="none", score=0.0, pct=pct)
        # 1) 정확 매칭(어느 후보든 성공하면 채택)
        for k in cand_keys:
            if k in self._lookup:
                return MatchResult(raw, index, self.ingredients[self._lookup[k]], "exact", 1.0, pct)
        # 1.5) 표기 변형 매칭(실록세인/실록산, 시어/쉐어 등) — 퍼지보다 정밀
        for k in cand_keys:
            fk = _fold(k)
            if fk in self._folded_lookup:
                return MatchResult(raw, index, self.ingredients[self._folded_lookup[fk]], "variant", 0.95, pct)
        # 2) 퍼지 매칭(후보 중 최고 점수)
        best = None
        for k in cand_keys:
            cands = difflib.get_close_matches(k, self._keys, n=1, cutoff=FUZZY_THRESHOLD)
            if cands:
                score = difflib.SequenceMatcher(None, k, cands[0]).ratio()
                if best is None or score > best[1]:
                    best = (cands[0], score)
        if best:
            return MatchResult(raw, index, self.ingredients[self._lookup[best[0]]], "fuzzy", best[1], pct)
        # 3) 부분 매칭(액티브 한정)
        for k in cand_keys:
            for ck, ing_id in self._contain_keys:
                if ck in k:
                    return MatchResult(raw, index, self.ingredients[ing_id], "contains", 0.8, pct)
        # 4) 미확인 — 추정 금지
        return MatchResult(raw, index, None, "none", 0.0, pct)

    def match_list(self, raw_list) -> tuple[list[MatchResult], list[MatchResult]]:
        """(matched, unmatched) 튜플 반환. index는 전성분 순서 유지.
        - 문자열 입력 허용(LLM이 통짜 문자열로 넘기는 실전 케이스): 쉼표/줄바꿈/·/세미콜론 분리
        - 중복 성분 제거(OCR 중복 입력 대비): 최초 등장(=최고 함량 인덱스)만 유지
        """
        items = coerce_ingredient_list(raw_list)
        results, seen_ids, seen_raw = [], set(), set()
        for i, r in enumerate(items):
            m = self.match_one(r, i)
            if m.matched:
                if m.ingredient.id in seen_ids:
                    continue
                seen_ids.add(m.ingredient.id)
            else:
                key = _norm_key(r)
                if key in seen_raw:
                    continue
                seen_raw.add(key)
            results.append(m)
        return [r for r in results if r.matched], [r for r in results if not r.matched]


_SPLIT_RE = re.compile(r"[,\n;·]|(?:\s{2,})")


def coerce_ingredient_list(raw) -> list[str]:
    """LLM 비정형 입력 방어: 문자열이면 구분자로 분리, 리스트면 각 항목 정리.
    '/'는 성분명 자체에 쓰이므로(카프릴릭/카프릭트라이글리세라이드) 구분자로 쓰지 않는다."""
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = _SPLIT_RE.split(raw)
    elif isinstance(raw, (list, tuple)):
        parts = []
        for item in raw:
            if isinstance(item, str) and _SPLIT_RE.search(item):
                parts.extend(_SPLIT_RE.split(item))
            else:
                parts.append(str(item) if item is not None else "")
    else:
        parts = [str(raw)]
    return [p.strip() for p in parts if p and p.strip()]
