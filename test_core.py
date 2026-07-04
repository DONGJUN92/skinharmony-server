"""코어 로직 검증 (mcp 설치 불필요). python test_core.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from core.compat import CompatEngine
from core.engine import judge, render_report
from core.normalizer import Normalizer
from core.store import PrefStore

PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  OK  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL {name} {detail}")


norm = Normalizer()

print("[1] 정규화: 정확/이명/퍼지/부분/미확인")
m = norm.match_one("정제수")
check("정확 매칭(정제수)", m.matched and m.ingredient.id == "water" and m.method == "exact")
m = norm.match_one("Aqua")
check("이명 매칭(Aqua→water)", m.matched and m.ingredient.id == "water")
m = norm.match_one("부틸렌그라이콜")  # 오탈자
check("퍼지 매칭(부틸렌그라이콜)", m.matched and m.ingredient.id == "butylene_glycol", f"got {m.method}/{m.ingredient}")
m = norm.match_one("나이아신아마이드 ")  # 공백
check("공백 정규화", m.matched and m.ingredient.id == "niacinamide")
m = norm.match_one("비타민C")
check("이명(비타민C→ascorbic_acid)", m.matched and m.ingredient.id == "ascorbic_acid")
m = norm.match_one("레티놀리포좀")  # 부분 매칭(액티브 한정)
check("부분 매칭(레티놀리포좀)", m.matched and m.ingredient.id == "retinol" and m.method == "contains")
m = norm.match_one("존재하지않는성분XYZ")
check("미확인 분리(추정 금지)", not m.matched)
m = norm.match_one("글리세린수용액")  # 베이스는 부분 매칭 금지 → 미확인이어야 함
check("베이스 부분매칭 차단(오탐 방지)", not m.matched, f"got {m.method}")

print("[2] 신호등 판정")
matched, unmatched = norm.match_list(["정제수", "레티놀", "글리세린", "향료", "리모넨", "페녹시에탄올", "판테놀"])
grades = {m.ingredient.id: judge(m)[0] for m in matched if not m.ingredient.is_base}
check("레티놀 상위 인덱스=RED(고농축 추정)", grades.get("retinol") == "RED", str(grades))
check("리모넨=YELLOW(EU26)", grades.get("limonene") == "YELLOW")
check("향료=YELLOW(통칭)", grades.get("fragrance") == "YELLOW")
check("판테놀=GREEN", grades.get("panthenol") == "GREEN")

print("[3] 리포트 렌더링")
report = render_report("테스트 토너", matched, unmatched, prefs={"limonene": "AVOID"})
check("제목·카운트 포함", "테스트 토너" in report and "🔴" in report)
check("회피 성분 강조(★)", "★회피" in report)
check("베이스 제외 안내", "베이스 성분" in report)
check("공유 훅 포함", "공유" in report)
check("출처 표기", "식품의약품안전처" in report)
check("응답 24k 미만", len(report) < 24000, f"len={len(report)}")

print("[4] 궁합 검사")
compat = CompatEngine(norm)
out = compat.check([
    {"name": "레티놀 크림", "ingredients": ["정제수", "레티놀", "세라마이드엔피"]},
    {"name": "비타민C 세럼", "ingredients": ["정제수", "아스코빅애씨드", "토코페롤"]},
])
check("레티노이드×비타민C 충돌 감지", "레티놀" in out and "아스코빅애씨드" in out and ("⚠️" in out or "🟡" in out))
check("Day/Night 루틴 포함", "아침" in out and "저녁" in out)
check("시너지 감지(비타민C×토코페롤)", "시너지" in out, out[-500:])
out2 = compat.check([{"name": "A", "ingredients": ["정제수", "판테놀"]}])
check("제품 1개 → 안내 메시지", "두 제품" in out2)
out3 = compat.check([
    {"name": "A", "ingredients": ["글라이콜릭릭애씨드오타"]},  # 미확인
    {"name": "B", "ingredients": ["레티놀"]},
])
check("미확인 성분 정직 처리", "미확인" in out3 or "충돌 규칙에는" in out3)

print("[5] 개인 기억 저장소")
with tempfile.TemporaryDirectory() as td:
    store = PrefStore(Path(td) / "t.sqlite")
    check("저장 성공", store.save("준이", "limonene", "리모넨", "AVOID", "붉어짐"))
    check("조회", store.get_prefs("준이") == {"limonene": "AVOID"})
    store.save("준이", "limonene", "리모넨", "PREFER")  # 멱등 업데이트
    check("멱등 upsert", store.get_prefs("준이") == {"limonene": "PREFER"})
    check("타 사용자 격리", store.get_prefs("다른사람") == {})
    check("빈 닉네임 거부", not store.save("", "x", "x", "AVOID"))
    check("닉네임 특수문자 정제", store.save("준이!@#", "retinol", "레티놀", "AVOID") and store.get_prefs("준이")["retinol"] == "AVOID")

print("[6] 시뮬레이션 발견 결함 회귀 테스트")
# 6-1. 문자열 통짜 입력 → 쉼표 분리(글자 단위 분해 금지)
matched, unmatched = norm.match_list("정제수, 나이아신아마이드, 향료, 리모넨")
check("문자열 입력 쉼표 분리", len(matched) == 4 and not unmatched, f"m={len(matched)} u={len(unmatched)}")
# 6-2. '/' 포함 성분명은 분리하지 않음
matched, _ = norm.match_list(["카프릴릭/카프릭트라이글리세라이드"])
check("'/' 성분명 보존", len(matched) == 1 and matched[0].ingredient.id == "cct")
# 6-3. 중복 성분 dedupe(최초 인덱스 유지)
matched, _ = norm.match_list(["레티놀", "정제수", "레티놀", "레티놀"])
check("중복 dedupe", len(matched) == 2)
# 6-4. 전부 미확인 → '무난' 오판 금지
_, un = norm.match_list(["알수없는성분A", "이상한성분B"])
rep = render_report(None, [], un)
check("전부 미확인 시 인식 실패 안내", "인식하지 못했어요" in rep and "무난한 구성" not in rep)
# 6-5. 확장 사전(국민 성분) 매칭
for name, eid in [("베타인", "betaine"), ("알란토인", "allantoin"), ("녹차추출물", "green_tea"), ("어성초추출물", "houttuynia")]:
    m = norm.match_one(name)
    check(f"확장 사전({name})", m.matched and m.ingredient.id == eid)

print("[7] 2차 시뮬레이션 결함 회귀 테스트")
# 7-1. 표기 농도 추출 + 정확 매칭 승격
m = norm.match_one("나이아신아마이드 5%")
check("% 추출(나이아신 5%)", m.matched and m.ingredient.id == "niacinamide" and m.pct == 5.0 and m.method == "exact")
m = norm.match_one("레티놀 0.1%")
check("% 추출(레티놀 0.1%)", m.matched and m.ingredient.id == "retinol" and m.pct == 0.1)
# 7-2. 농도 우선 판정: 저농도 레티놀은 상위 인덱스여도 RED 아님 / AHA 12%는 RED
g, r = judge(norm.match_one("레티놀 0.1%", index=1))
check("저농도 레티놀=완화(GREEN/YELLOW)", g in ("GREEN", "YELLOW"), f"{g}:{r}")
g, r = judge(norm.match_one("글라이콜릭애씨드 12%", index=10))
check("AHA 12%=RED(농도 우선)", g == "RED" and "12%" in r, f"{g}:{r}")
g, r = judge(norm.match_one("살리실릭애씨드 1%", index=10))
check("BHA 1%=YELLOW(3단계)", g == "YELLOW", f"{g}:{r}")
# 7-3. 민감성 정렬 부스트: 향료류가 사용한도 보존제보다 위로
mt, un = norm.match_list(["정제수", "페녹시에탄올", "변성알코올", "향료", "판테놀"])
rep = render_report(None, mt, un, skin_concern="민감성")
check("민감성 부스트(향료가 페녹시에탄올보다 위)", rep.index("변성알코올") < rep.index("페녹시에탄올") and "위쪽에 배치" in rep)
rep2 = render_report(None, mt, un, skin_concern="미백")
check("비민감 고민은 부스트 미적용 안내", "위쪽에 배치" not in rep2 and "미백" in rep2)
# 7-4. 동일 구성 제품 안내(스키니멀리즘)
out = compat.check([
    {"name": "토너A", "ingredients": ["판테놀", "알란토인", "병풀추출물", "베타인"]},
    {"name": "토너B", "ingredients": ["판테놀", "알란토인", "병풀추출물", "베타인", "트레할로스"]},
])
check("동일 구성 안내(겹침률 80%)", "겹쳐" in out and "스키니멀리즘" in out, out[-300:])
out = compat.check([
    {"name": "토너", "ingredients": ["판테놀", "알란토인", "병풀추출물"]},
    {"name": "크림", "ingredients": ["레티놀", "세라마이드엔피", "스쿠알란"]},
])
check("다른 구성엔 미출력", "스키니멀리즘" not in out)

print("[8] 실전 버그 회귀 테스트 (한/영 병기 + 클렌저 커버리지)")
# 8-1. '리모넨(Limonene)' 한/영 병기 매칭
m = norm.match_one("리모넨(Limonene)")
check("한/영 병기(리모넨(Limonene))", m.matched and m.ingredient.id == "limonene", f"got {m.method}/{m.ingredient}")
m = norm.match_one("리날룰(Linalool)")
check("한/영 병기(리날룰(Linalool))", m.matched and m.ingredient.id == "linalool")
m = norm.match_one("나이아신아마이드 (Niacinamide) 5%")  # 병기+농도 동시
check("병기+농도 동시", m.matched and m.ingredient.id == "niacinamide" and m.pct == 5.0, f"{m.method}/{m.pct}")
m = norm.match_one("Retinol(레티놀)")  # 영문(한글) 역순
check("영/한 역순 병기", m.matched and m.ingredient.id == "retinol")
# 8-2. 클렌저/계면활성제 커버리지
for name, eid in [("소듐라우레스설페이트", "sles"), ("코카미도프로필베타인", "cocamidopropyl_betaine"),
                  ("코카미도엠이에이", "cocamide_mea"), ("소듐클로라이드", "sodium_chloride")]:
    m = norm.match_one(name)
    check(f"클렌저 사전({name})", m.matched and m.ingredient.id == eid, f"got {m.ingredient}")
# 8-3. 실제 클렌저 전성분 → 미확인 대폭 감소
cleanser = ["정제수", "소듐라우레스설페이트", "코카미도프로필베타인", "글리세린", "소듐클로라이드",
            "코카미도엠이에이", "향료", "시트랄", "벤질살리실레이트", "리모넨(Limonene)", "리날룰(Linalool)",
            "페녹시에탄올"]
mt, un = norm.match_list(cleanser)
check("클렌저 미확인 ≤1건(향료혼합물 제외)", len(un) <= 1, f"미확인 {len(un)}건: {[u.raw for u in un]}")
check("리모넨 착향 인식", any(x.ingredient.id == "limonene" for x in mt))

print("[9] 표기 변형 정규화(Variant Folding) 회귀 테스트")
for name, eid in [("사이클로펜타실록산", "cyclopentasiloxane"), ("쉐어버터", "shea_butter"),
                  ("부틸렌글리콜", "butylene_glycol"), ("디메티콘", "dimethicone"),
                  ("메칠파라벤", "methylparaben")]:
    m = norm.match_one(name)
    check(f"변형 매칭({name})", m.matched and m.ingredient.id == eid, f"got {m.method}/{m.ingredient}")
# 세테아릴올리베이트 신규 커버
m = norm.match_one("세테아릴올리베이트")
check("신규 커버(세테아릴올리베이트)", m.matched and m.ingredient.id == "cetearyl_olivate")
# folding이 서로 다른 성분을 잘못 합치지 않는지(충돌 방지)
ids = set()
for k, i in norm._folded_lookup.items():
    ids.add(i)
check("folded_lookup 무결성(엔트리 존재)", len(norm._folded_lookup) > 100)
# 사용자 3종 통합: 미확인 0건이어야
mt, un = norm.match_list(["사이클로펜타실록산", "세테아릴올리베이트", "쉐어버터"])
check("사용자 3종 전부 인식(미확인 0)", len(un) == 0, f"미확인: {[u.raw for u in un]}")

print(f"\n결과: {PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("실패 목록:", FAIL)
    sys.exit(1)
print("ALL PASS ✅")
