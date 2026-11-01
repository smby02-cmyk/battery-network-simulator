"""모든 가정과 이름표. 케이스 자료 6·7·10·14 기준 (INU GLR Case Study 「탄소 국경 위의 배터리 공장」).

코드 안에 숫자를 직접 쓰지 않고 이 파일에서만 바꾼다.
"""

DATA_FILE = "data/battery_supply_chain_SIMPLE.xlsx"

YEARS = list(range(2026, 2046))
BASE_YEAR = 2026
WACC = 0.09            # 자료 10: 달러 기준, 2026년 시점 할인, 잔존가치 0
EUR_USD = 1.10         # 자료 10
DUAL_SOURCING = 0.70   # 자료 10: OEM 거점 수요의 최대 70%

# ---- 원가 (자료 10) ----
MATERIAL_2026 = 50.0            # $/kWh, 양품 기준 → 수율로 나눔
MATERIAL_DECLINE = (0.985, 0.995)   # 2030년까지 연 −1.5%, 이후 연 −0.5%
PRICE_DECLINE = (0.985, 0.995)      # 판매가격 동일 추세
CONVERSION_LEARNING = 0.99          # 가공비 2035년까지 연 −1%
CONVERSION_LEARNING_YEARS = 9
ELEC_KWH_PER_KWH_CELL = 38.8        # 셀 1kWh당 전력 사용량
FIXED_OPEX_GROWTH = 0.015
RAMP_MIN_FIXED = 0.60               # 램프업 중 고정비 최소 비율
INVENTORY_RATE = 0.12               # 연 12%
SAFETY_STOCK_DAYS = 7

# ---- 탄소 (자료 6·7·9) ----
MATERIAL_EMBEDDED_KG = 45.6
CARBON_PRICE_2026 = 75.0            # €/t
CARBON_PRICE_GROWTH = 0.03
CBAM_SHARE_BASE = 0.25              # 내재배출 중 과금 비중
CAP_2030, CAP_2035 = 65.0, 60.0     # ver2 탄소발자국 상한 (kg/kWh, 운송 포함)

# ---- 공장 (자료 6·10) ----
OCHANG = "F_KR_LGES_OCHANG"
WROCLAW = "F_EU_PL_LGES_WROCLAW"
WROCLAW_EXP = "F_EU_PL_WROCLAW_EXP"
EXISTING = [OCHANG, WROCLAW]
CANDIDATES = ["F_EU_PL_WROCLAW_EXP", "F_EU_HU_DEBRECEN", "F_EU_DE_BRANDENBURG", "F_EU_FR_DOUVRIN",
              "F_EU_ES_ZARAGOZA", "F_EU_SE_SKELLEFTEA", "F_EU_PT_SINES", "F_EU_CZ_OSTRAVA"]

PLANT_NAME = {
    "F_KR_LGES_OCHANG": "오창 (한국)", "F_EU_PL_LGES_WROCLAW": "브로츠와프 (폴란드)",
    "F_EU_PL_WROCLAW_EXP": "브로츠와프 증설 (폴란드)", "F_EU_HU_DEBRECEN": "데브레첸 (헝가리)",
    "F_EU_DE_BRANDENBURG": "브란덴부르크 (독일)", "F_EU_FR_DOUVRIN": "두브랭 (프랑스)",
    "F_EU_ES_ZARAGOZA": "사라고사 (스페인)", "F_EU_SE_SKELLEFTEA": "셸레프테오 (스웨덴)",
    "F_EU_PT_SINES": "시네스 (포르투갈)", "F_EU_CZ_OSTRAVA": "오스트라바 (체코)",
}
TAX = {"F_KR_LGES_OCHANG": .24, "F_EU_PL_LGES_WROCLAW": .19, "F_EU_PL_WROCLAW_EXP": .19, "F_EU_HU_DEBRECEN": .09,
       "F_EU_DE_BRANDENBURG": .30, "F_EU_FR_DOUVRIN": .25, "F_EU_ES_ZARAGOZA": .25, "F_EU_SE_SKELLEFTEA": .206,
       "F_EU_PT_SINES": .21, "F_EU_CZ_OSTRAVA": .21}
SUBSIDY = {"F_EU_PL_WROCLAW_EXP": .10, "F_EU_HU_DEBRECEN": .15, "F_EU_DE_BRANDENBURG": .15, "F_EU_FR_DOUVRIN": .25,
           "F_EU_ES_ZARAGOZA": .15, "F_EU_SE_SKELLEFTEA": .10, "F_EU_PT_SINES": .15, "F_EU_CZ_OSTRAVA": .12}
DEPRECIATION_YEARS = 10
# 투자 집행·가동 일정 (자료 10)
GREENFIELD_CAPEX = {2027: .4, 2028: .6}
GREENFIELD_RAMP = {2029: .5, 2030: .85}          # 2031년부터 100%
GREENFIELD_START = 2029
EXPANSION_CAPEX = {2027: .7, 2028: .3}
EXPANSION_RAMP = {2028: .5}                      # 2029년부터 100%
EXPANSION_START = 2028

# ---- 시나리오 (자료 14) ----
SCENARIOS = {
    "base": "기준 (ver1: 규제 미시행)",
    "cap": "탄소발자국 상한 (ver2: 규제 시행)",
    "high": "고탄소",
    "slow": "수요 둔화",
    "onshore": "역내생산 요건",
}
HIGH_CARBON_MULT = 1.5      # 탄소가격 ×1.5, 2030년부터 한국산 CBAM 100%
OEM_INTERNAL_THRESHOLD = 50.0   # kg/kWh, 초과분 차감·미달분 가산 (양방향)
SLOW_GROWTH_MULT = 0.5
ONSHORE_PENALTY = 6.0       # $/kWh, 2030년부터 한국산 셀 → 유럽 고객
POLICY_YEAR = 2030

# 지도 색 (동원홈푸드 발표 양식과 통일)
NAVY, BLUE, SKY, GRAY = "#1F3864", "#2F6BD8", "#7096DB", "#6B7280"
