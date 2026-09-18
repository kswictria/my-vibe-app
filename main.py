
import re
import requests
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import plotly.express as px

st.set_page_config(page_title="전국 인구 구조 지도", layout="wide")

# ==================================================
# 🐱 마우스를 따라다니는 고양이
# ==================================================
components.html("""
<div id="cat" style="
    position: fixed;
    left: 20px;
    top: 20px;
    font-size: 30px;
    z-index: 999999;
    pointer-events: none;
    transition: left 0.08s linear, top 0.08s linear;
">🐱</div>

<script>
const cat = document.getElementById("cat");

document.addEventListener("mousemove", function(event) {
    cat.style.left = (event.clientX + 15) + "px";
    cat.style.top = (event.clientY + 15) + "px";
});
</script>
""", height=0)

st.title("🗺️ 전국 인구 구조 지도")
st.caption("시군구별 인구 비율 분석 (행정안전부 주민등록 인구)")

POP_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
GEO_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"


@st.cache_data(show_spinner="인구 데이터를 불러오는 중입니다...")
def load_population():
    return pd.read_csv(POP_URL, dtype={"코드": str})


@st.cache_data(show_spinner="지도 경계를 불러오는 중입니다...")
def load_geojson():
    response = requests.get(GEO_URL, timeout=30)
    response.raise_for_status()
    return response.json()


df = load_population()
geojson = load_geojson()

# ==================================================
# 1. 최신 연도 데이터
# ==================================================
latest_year = int(df["연도"].max())
df = df[df["연도"] == latest_year].copy()

# ==================================================
# 2. 연령별 인구 열 찾기
# ==================================================
total_cols = [c for c in df.columns if c.startswith("계_")]


def age_of(col):
    m = re.match(r"계_(\d+)세", col)
    return int(m.group(1)) if m else None


# 65세 이상
elderly_cols = [
    c for c in total_cols
    if age_of(c) is not None and age_of(c) >= 65
]

# 19~39세 청년
youth_cols = [
    c for c in total_cols
    if age_of(c) is not None and 19 <= age_of(c) <= 39
]

# ==================================================
# 3. 전체 인구·고령 인구·청년 인구 계산
# ==================================================
df["전체인구"] = df[total_cols].sum(axis=1)

df["고령인구"] = df[elderly_cols].sum(axis=1)

df["청년인구"] = df[youth_cols].sum(axis=1)

# ==================================================
# 4. 시군구 단위 집계
# ==================================================
df["시군구코드"] = df["코드"].str[:5]

grouped = (
    df.groupby("시군구코드")[
        ["전체인구", "고령인구", "청년인구"]
    ]
    .sum()
    .reset_index()
)

grouped["고령화율"] = (
    grouped["고령인구"] / grouped["전체인구"] * 100
).round(2)

grouped["청년비율"] = (
    grouped["청년인구"] / grouped["전체인구"] * 100
).round(2)

# ==================================================
# 5. 지도 경계의 지역 이름 연결
# ==================================================
names = pd.DataFrame([
    {
        "시군구코드": str(f["properties"]["코드"]),
        "시군구": f["properties"]["시군구"],
        "시도": f["properties"]["시도"],
    }
    for f in geojson["features"]
])

merged = grouped.merge(
    names,
    on="시군구코드",
    how="left"
)

# ==================================================
# 6. 모드 선택
# ==================================================
st.sidebar.header("⚙️ 지도 설정")

mode = st.sidebar.radio(
    "인구 비율 모드",
    ["고령화율", "청년 비율"]
)

if mode == "고령화율":
    value_col = "고령화율"
    population_col = "고령인구"
    title_text = "65세 이상 인구 비율"
    legend_title = f"고령화율 ({latest_year}년)"
    map_title = f"🗺️ 전국 고령화 지도 ({latest_year}년)"

    BINS = [0, 19, 23, 28, 38, 100]
    LABELS = [
        "19% 미만",
        "19~23%",
        "23~28%",
        "28~38%",
        "38% 이상"
    ]

    COLORS = {
        "19% 미만": "#fee6ce",
        "19~23%": "#fdc086",
        "23~28%": "#f79646",
        "28~38%": "#e8590c",
        "38% 이상": "#a63603",
    }

else:
    value_col = "청년비율"
    population_col = "청년인구"
    title_text = "19~39세 청년 인구 비율"
    legend_title = f"청년 비율 ({latest_year}년)"
    map_title = f"🗺️ 전국 청년 비율 지도 ({latest_year}년)"

    # 청년 비율의 구간은 고령화율과 별도로 설정
    BINS = [0, 10, 15, 20, 25, 100]
    LABELS = [
        "10% 미만",
        "10~15%",
        "15~20%",
        "20~25%",
        "25% 이상"
    ]

    COLORS = {
        "10% 미만": "#deebf7",
        "10~15%": "#9ecae1",
        "15~20%": "#6baed6",
        "20~25%": "#3182bd",
        "25% 이상": "#08519c",
    }

# ==================================================
# 7. 선택한 모드에 맞는 단계 구분
# ==================================================
merged["단계"] = pd.cut(
    merged[value_col],
    bins=BINS,
    labels=LABELS,
    right=False
)

# ==================================================
# 8. 지도 생성
# ==================================================
st.subheader(map_title)

fig = px.choropleth(
    merged,
    geojson=geojson,
    locations="시군구코드",
    featureidkey="properties.코드",
    color="단계",
    category_orders={"단계": LABELS},
    color_discrete_map=COLORS,
    hover_name="시군구",
    hover_data={
        value_col: True,
        "시도": True,
        "시군구코드": False,
        "단계": False,
    },
    labels={
        value_col: title_text
    },
)

fig.update_geos(
    fitbounds="locations",
    visible=False
)

fig.update_layout(
    margin=dict(l=0, r=0, t=10, b=0),
    height=700,
    legend_title_text=legend_title,
)

st.plotly_chart(fig, width="stretch")

# ==================================================
# 9. 선택한 모드의 순위 표
# ==================================================
c1, c2 = st.columns(2)

cols = ["시도", "시군구", value_col, population_col]

with c1:
    st.subheader(f"🔴 {title_text} 높은 곳 10")

    st.dataframe(
        merged.nlargest(10, value_col)[cols]
        .reset_index(drop=True),
        width="stretch"
    )

with c2:
    st.subheader(f"🟢 {title_text} 낮은 곳 10")

    st.dataframe(
        merged.nsmallest(10, value_col)[cols]
        .reset_index(drop=True),
        width="stretch"
    )

# ==================================================
# 10. 기준 안내
# ==================================================
st.info(
    "현재 청년 비율 모드는 19~39세를 기준으로 계산합니다. "
    "청년 연령 기준은 분석 목적에 따라 변경할 수 있습니다."
)
