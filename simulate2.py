"""2차 시뮬레이션 — 1차에서 다루지 않은 실전 시나리오.

F: 실제 사용 패턴 확장 (영문 INCI / OCR 줄바꿈 / 농도 % 표기 / 선크림)
G: 대화 품질 (skin_concern 실효성 / 선호 강조 / 조회 다양성)
H: 궁합 특수 케이스 (동일 제품 / 액티브 없음 / 시너지만)
"""
import sys, os, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ["SKINHARMONY_DB"] = str(Path(__file__).parent / "sim3.sqlite")
import server


def run(label, fn, **kw):
    t0 = time.perf_counter()
    try:
        out = fn(**kw)
        ms = (time.perf_counter() - t0) * 1000
        print(f"\n{'='*70}\n[{label}]  ({ms:.1f}ms, {len(out)} chars)\n{'-'*70}\n{out}")
        return out
    except Exception as e:
        print(f"\n{'='*70}\n[{label}]  💥 {type(e).__name__}: {e}")
        return f"EXC:{e}"


print("#### F. 실제 사용 패턴 확장 ####")
run("F1. 영문 INCI 문자열(해외직구 제품)", server.analyze_ingredients,
    ingredients="Water, Glycerin, Niacinamide, Retinol, Fragrance, Limonene",
    product_name="해외 세럼")
run("F2. OCR 줄바꿈 붙여넣기", server.analyze_ingredients,
    ingredients="정제수\n글리세린\n레티날\n판테놀\n향료")
run("F3. 농도 % 표기(마케팅 표기)", server.analyze_ingredients,
    ingredients=["정제수", "나이아신아마이드 5%", "글라이콜릭애씨드 12%", "레티놀 0.1%", "판테놀"],
    product_name="고농축 앰플")
run("F4. 선크림(자외선차단 한도)", server.analyze_ingredients,
    ingredients=["정제수", "징크옥사이드", "티타늄디옥사이드", "에틸헥실메톡시신나메이트", "글리세린", "향료"],
    product_name="선크림")

print("\n#### G. 대화 품질 ####")
run("G1. 민감성 고민 반영(정렬 실효성)", server.analyze_ingredients,
    ingredients=["정제수", "페녹시에탄올", "변성알코올", "향료", "리모넨", "판테놀", "글라이콜릭애씨드"],
    skin_concern="민감성")
server.remember_ingredient(ingredient="판테놀", preference="PREFER", user_key="유나")
run("G2. 선호(👍) 강조 리포트", server.analyze_ingredients,
    ingredients=["정제수", "판테놀", "글리세린", "향료"], user_key="유나")
run("G3. 조회: 사용한도 성분", server.search_cosmetic_info, query_name="페녹시에탄올")
run("G4. 조회: 영문+오탈자", server.search_cosmetic_info, query_name="retinal")
run("G5. 조회: 베이스 성분", server.search_cosmetic_info, query_name="글리세린")

print("\n#### H. 궁합 특수 케이스 ####")
run("H1. 동일 성분 제품끼리", server.check_compatibility, products=[
    {"name": "토너A", "ingredients": ["정제수", "글리세린", "판테놀"]},
    {"name": "토너B", "ingredients": ["정제수", "글리세린", "판테놀"]}])
run("H2. 시너지만 존재", server.check_compatibility, products=[
    {"name": "비타민C 앰플", "ingredients": ["정제수", "아스코빅애씨드"]},
    {"name": "토코페롤 크림", "ingredients": ["정제수", "토코페롤"]}])
run("H3. 궁합 데모(빈 호출)", server.check_compatibility, products=[])
run("H4. 단일 dict로 호출(LLM 실수)", server.check_compatibility, products={
    "name": "크림", "ingredients": ["레티놀"]})

Path(os.environ["SKINHARMONY_DB"]).unlink(missing_ok=True)
print("\n[2차 시뮬레이션 종료]")
