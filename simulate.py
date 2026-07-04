"""실사용 시뮬레이션 — AI 채팅에서 발생할 호출 패턴 재현 + 3관점(유저/서버/개발자) 평가용.

python simulate.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import os
os.environ["SKINHARMONY_DB"] = str(Path(__file__).parent / "sim_prefs.sqlite")
import server  # noqa: E402

# 실제 시판 토너류에 준하는 현실적 전성분(30개+, 사전 밖 성분 다수 포함)
REAL_TONER = [
    "정제수", "부틸렌글라이콜", "글리세린", "다이프로필렌글라이콜", "베타인",
    "판테놀", "소듐하이알루로네이트", "알란토인", "마데카소사이드", "병풀추출물",
    "녹차추출물", "위치하젤추출물", "어성초추출물", "카프릴릭/카프릭트라이글리세라이드",
    "폴리글리세릴-10라우레이트", "하이드록시에틸셀룰로오스", "잔탄검", "카보머",
    "트로메타민", "에틸헥실글리세린", "1,2-헥산다이올", "페녹시에탄올",
    "다이소듐이디티에이", "시트릭애씨드", "향료", "리날룰", "리모넨",
]
REAL_SERUM = [
    "정제수", "나이아신아마이드", "부틸렌글라이콜", "글리세린", "레티날",
    "아데노신", "세라마이드엔피", "콜레스테롤", "하이드로제네이티드레시틴",
    "토코페롤", "잔탄검", "1,2-헥산다이올",
]


def run(label, fn, *args, **kw):
    t0 = time.perf_counter()
    try:
        out = fn(*args, **kw)
        ms = (time.perf_counter() - t0) * 1000
        print(f"\n{'='*70}\n[{label}]  ({ms:.1f}ms, {len(out)} chars)\n{'-'*70}")
        print(out)
        return out, ms
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        print(f"\n{'='*70}\n[{label}]  💥 EXCEPTION ({ms:.1f}ms): {type(e).__name__}: {e}")
        return f"EXCEPTION: {e}", ms


print("#" * 70)
print("# 시나리오 A: 심사위원 첫 진입(데모) → 실제 성분 붙여넣기")
print("#" * 70)
run("A1. 데모(예시로 보여줘)", server.analyze_ingredients, demo=True)
run("A2. 실제 토너 27성분 분석", server.analyze_ingredients, ingredients=REAL_TONER, product_name="독도 토너(가정)")

print("\n" + "#" * 70)
print("# 시나리오 B: LLM의 비정형 호출 (실전에서 반드시 발생)")
print("#" * 70)
run("B1. ingredients를 문자열로 전달", server.analyze_ingredients,
    ingredients="정제수, 나이아신아마이드, 향료, 리모넨, 페녹시에탄올")
run("B2. 빈 리스트", server.analyze_ingredients, ingredients=[])
run("B3. preference를 한국어로", server.remember_ingredient,
    ingredient="리모넨", preference="회피", user_key="준이")
run("B4. compat에 ingredients 문자열", server.check_compatibility, products=[
    {"name": "레티놀 크림", "ingredients": "정제수, 레티놀, 세라마이드엔피"},
    {"name": "비타민C 세럼", "ingredients": "정제수, 비타민C, 토코페롤"},
])
run("B5. compat에 제품 하나만", server.check_compatibility,
    products=[{"name": "A", "ingredients": ["레티놀"]}])

print("\n" + "#" * 70)
print("# 시나리오 C: 개인화 루프 (기억 → 재분석 강조)")
print("#" * 70)
run("C1. 회피 저장", server.remember_ingredient,
    ingredient="리모넨", preference="AVOID", user_key="지수", reason="붉어짐")
run("C2. 선호 저장(이명 입력)", server.remember_ingredient,
    ingredient="비타민B3", preference="PREFER", user_key="지수")
run("C3. 개인화 재분석(★강조 확인)", server.analyze_ingredients,
    ingredients=REAL_TONER, product_name="독도 토너", user_key="지수")
run("C4. 성분 조회+개인 표시", server.search_cosmetic_info, query_name="리모넨", user_key="지수")

print("\n" + "#" * 70)
print("# 시나리오 D: 궁합 히어로 + 3제품")
print("#" * 70)
run("D1. 레티날 세럼 × AHA 토너 × 비타민C", server.check_compatibility, products=[
    {"name": "레티날 세럼", "ingredients": REAL_SERUM},
    {"name": "AHA 토너", "ingredients": ["정제수", "글라이콜릭애씨드", "글리세린"]},
    {"name": "비타민C 앰플", "ingredients": ["정제수", "아스코빅애씨드", "토코페롤"]},
])

print("\n" + "#" * 70)
print("# 시나리오 E: 엣지/스트레스")
print("#" * 70)
run("E1. 미확인 성분만 5개", server.analyze_ingredients,
    ingredients=["알수없는성분A", "이상한성분B", "OCR오류텍스트", "ㅁㄴㅇㄹ", "xyz123"])
big = REAL_TONER * 5  # 135개 성분(OCR 중복 등 극단 케이스)
run("E2. 성분 135개 대량 입력", server.analyze_ingredients, ingredients=big)
run("E3. 잘못된 preference", server.remember_ingredient,
    ingredient="향료", preference="LOVE", user_key="준이")
run("E4. 닉네임 없이 기억 요청", server.remember_ingredient,
    ingredient="향료", preference="AVOID", user_key="")
run("E5. 성분 사전 밖 조회", server.search_cosmetic_info, query_name="말도안되는성분명")

# 정리
Path(os.environ["SKINHARMONY_DB"]).unlink(missing_ok=True)
print("\n[시뮬레이션 종료]")
