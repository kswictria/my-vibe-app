
import re
import requests
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import plotly.express as px

st.set_page_config(
    page_title="전국 인구 구조 지도",
    layout="wide"
)

# ==================================================
# 🐱 고양이 효과
# ==================================================

components.html("""
<!DOCTYPE html>
<html>
<head>
<style>
html, body {
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: transparent;
}

#cat {
    position: absolute;
    font-size: 36px;
    z-index: 999999;
    pointer-events: none;
    left: 0;
    top: 0;
    transform: translate(-100px, -100px);
    transition: left 0.12s ease-out, top 0.12s ease-out;
    animation: catWiggle 0.5s infinite alternate;
}

@keyframes catWiggle {
    from {
        transform: rotate(-5deg);
    }
    to {
        transform: rotate(5deg);
    }
}

.heart {
    position: absolute;
    font-size: 25px;
    pointer-events: none;
    animation: heartUp 1s ease-out forwards;
    z-index: 999998;
}

@keyframes heartUp {
    0% {
        opacity: 1;
        transform: translateY(0) scale(1);
    }
    100% {
        opacity: 0;
        transform: translateY(-100px) scale(1.5);
    }
}
</style>
</head>

<body>

<div id="cat">🐱</div>

<script>
const cat = document.getElementById("cat");

document.addEventListener("mousemove", function(event) {
    cat.style.left = (event.clientX + 10) + "px";
    cat.style.top = (event.clientY + 10) + "px";
});

document.addEventListener("click", function(event) {
    const heart = document.createElement("div");

    heart.className = "heart";
    heart.innerHTML = "💗";
    heart.style.left = event.clientX + "px";
    heart.style.top = event.clientY + "px";

    document.body.appendChild(heart);

    setTimeout(function() {
        heart.remove();
    }, 1000);
});
</script>

</body>
</html>
""", height=700, scrolling=False)

# ==================================================
# 제목
# ==================================================

st.title("🗺️ 전국 인구 구조 지도")
st.caption(
    "시군구별 인구 비율 및 지역별 연령 분포 분석 "
    "(행정안전부 주민등록 인구)"
)

POP_URL = (
    "https://raw.githubusercontent.com/greatsong/modudata/"
    "main/data/population_yearly.csv.gz"
)

GEO_URL = (
    "https://raw.githubusercontent.com/greatsong/modudata/"
    "main/data/boundaries/sigungu_kr.geojson"
)

# ==================================================
# 데이터 불러오기
# ==================================================

@st.cache_data(show_spinner="인구 데이터를 불러오는 중입니다...")
def load_population():
    return pd.read_csv(
        POP_URL,
        dtype={"코드": str}
    )


@st.cache_data(show_spinner="지도 경계를 불러오는 중입니다...")
def load_geojson():
    response = requests.get(
        GEO_URL,
        timeout=30
    )
    response.raise_for_status()
    return response.json()


df = load_population()
geojson = load_geojson()

# ==================================================
# 1. 최신 연도 데이터
# ==================================================

latest_year = int(df["연도"].max())

df = df[
    df["연도"] == latest_year
].copy()

# ==================================================
# 2. 행정구역 이름 컬럼 자동 찾기
# ==================================================

possible_region_columns = [
    "행정구역",
    "행정구역명",
    "지역",
    "지역명",
    "읍면동",
    "읍·면·동"
]

region_name_col = None

for col in possible_region_columns:
    if col in df.columns:
        region_name_col = col
        break

# ==================================================
# 3. 연령별 인구 열 찾기
# ==================================================

total_cols = [
    c for c in df.columns
    if str(c).startswith("계_")
]


def age_of(col):
    match = re.match(
        r"계_(\d+)세",
        str(col)
    )

    if match:
        return int(match.group(1))

    return None


age_columns = []

for col in total_cols:
    age = age_of(col)

    if age is not None:
        age_columns.append((age, col))

age_columns = sorted(
    age_columns,
    key=lambda x: x[0]
)

elderly_cols = [
    col
    for age, col in age_columns
    if age >= 65
]

youth_cols = [
    col
    for age, col in age_columns
    if 19 <= age <= 39
]

# ==================================================
# 4. 전체 인구·고령 인구·청년 인구
# ==================================================

df["전체인구"] = df[total_cols].sum(
    axis=1,
    numeric_only=True
)

df["고령인구"] = df[elderly_cols].sum(
    axis=1,
    numeric_only=True
)

df["청년인구"] = df[youth_cols].sum(
    axis=1,
    numeric_only=True
)

# ==================================================
# 5. 시군구별 집계
# ==================================================

df["시군구코드"] = (
    df["코드"]
    .astype(str)
    .str[:5]
)

grouped = (
    df.groupby("시군구코드")[
        [
            "전체인구",
            "고령인구",
            "청년인구"
        ]
    ]
    .sum()
    .reset_index()
)

grouped["고령화율"] = (
    grouped["고령인구"]
    / grouped["전체인구"]
    * 100
).round(2)

grouped["청년비율"] = (
    grouped["청년인구"]
    / grouped["전체인구"]
    * 100
).round(2)

# ==================================================
# 6. 지역 이름 연결
# ==================================================

names = pd.DataFrame([
    {
        "시군구코드": str(
            feature["properties"]["코드"]
        ),
        "시군구": feature["properties"]["시군구"],
        "시도": feature["properties"]["시도"]
    }
    for feature in geojson["features"]
])

merged = grouped.merge(
    names,
    on="시군구코드",
    how="left"
)

# ==================================================
# 7. 지도 모드 선택
# ==================================================

st.sidebar.header("⚙️ 지도 설정")

mode = st.sidebar.radio(
    "인구 비율 모드",
    [
        "고령화율",
        "청년 비율"
    ]
)

if mode == "고령화율":

    value_col = "고령화율"
    population_col = "고령인구"

    title_text = "65세 이상 인구 비율"
    legend_title = f"고령화율 ({latest_year}년)"
    map_title = f"🗺️ 전국 고령화 지도 ({latest_year}년)"

    BINS = [
        0,
        19,
        23,
        28,
        38,
        100
    ]

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
        "38% 이상": "#a63603"
    }

else:

    value_col = "청년비율"
    population_col = "청년인구"

    title_text = "19~39세 청년 인구 비율"
    legend_title = f"청년 비율 ({latest_year}년)"
    map_title = f"🗺️ 전국 청년 비율 지도 ({latest_year}년)"

    BINS = [
        0,
        10,
        15,
        20,
        25,
        100
    ]

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
        "25% 이상": "#08519c"
    }

# ==================================================
# 8. 지도 단계 구분
# ==================================================

merged["단계"] = pd.cut(
    merged[value_col],
    bins=BINS,
    labels=LABELS,
    right=False
)

# ==================================================
# 9. 지도 생성
# ==================================================

st.subheader(map_title)

fig = px.choropleth(
    merged,
    geojson=geojson,
    locations="시군구코드",
    featureidkey="properties.코드",
    color="단계",
    category_orders={
        "단계": LABELS
    },
    color_discrete_map=COLORS,
    hover_name="시군구",
    hover_data={
        value_col: True,
        "시도": True,
        "시군구코드": False,
        "단계": False
    },
    labels={
        value_col: title_text
    }
)

fig.update_geos(
    fitbounds="locations",
    visible=False
)

fig.update_layout(
    margin=dict(
        l=0,
        r=0,
        t=10,
        b=0
    ),
    height=700,
    legend_title_text=legend_title
)

st.plotly_chart(
    fig,
    use_container_width=True
)

# ==================================================
# 10. 순위 표
# ==================================================

c1, c2 = st.columns(2)

rank_cols = [
    "시도",
    "시군구",
    value_col,
    population_col
]

with c1:

    st.subheader(
        f"🔴 {title_text} 높은 곳 10"
    )

    st.dataframe(
        merged.nlargest(
            10,
            value_col
        )[
            rank_cols
        ].reset_index(drop=True),
        use_container_width=True
    )

with c2:

    st.subheader(
        f"🟢 {title_text} 낮은 곳 10"
    )

    st.dataframe(
        merged.nsmallest(
            10,
            value_col
        )[
            rank_cols
        ].reset_index(drop=True),
        use_container_width=True
    )

# ==================================================
# 11. 지역별 연령 인구 분포
# ==================================================

st.markdown("---")

st.header("📊 지역별 연령 인구 분포")

st.caption(
    "시·도, 시·군·구, 읍·면·동을 선택하면 "
    "해당 지역의 연령별 인구를 확인할 수 있습니다."
)

if region_name_col is None:

    st.error(
        "행정구역 이름 컬럼을 찾을 수 없습니다."
    )

else:

    # ----------------------------------------------
    # 지역 이름 정리
    # ----------------------------------------------

    region_text = (
        df[region_name_col]
        .astype(str)
        .str.replace(
            r"\s*\([^)]*\)",
            "",
            regex=True
        )
        .str.strip()
    )

    # ----------------------------------------------
    # 시도 추출
    # ----------------------------------------------

    def get_region_part(text, index):
        parts = str(text).split()

        if len(parts) > index:
            return parts[index]

        return ""


    df["선택_시도"] = region_text.apply(
        lambda x: get_region_part(x, 0)
    )

    df["선택_시군구"] = region_text.apply(
        lambda x: get_region_part(x, 1)
    )

    df["선택_읍면동"] = region_text.apply(
        lambda x: " ".join(
            str(x).split()[2:]
        )
    )

    # ----------------------------------------------
    # 시도 선택
    # ----------------------------------------------

    sido_list = sorted(
        [
            x
            for x in df["선택_시도"].unique()
            if x and x != "nan"
        ]
    )

    selected_sido = st.selectbox(
        "① 시·도 선택",
        sido_list,
        index=None,
        placeholder="시·도를 선택하세요"
    )

    if selected_sido is not None:

        sido_df = df[
            df["선택_시도"] == selected_sido
        ].copy()

        # ------------------------------------------
        # 시군구 선택
        # ------------------------------------------

        sigungu_list = sorted(
            [
                x
                for x in sido_df["선택_시군구"].unique()
                if x and x != "nan"
            ]
        )

        selected_sigungu = st.selectbox(
            "② 시·군·구 선택",
            sigungu_list,
            index=None,
            placeholder="시·군·구를 선택하세요"
        )

        if selected_sigungu is not None:

            sigungu_df = sido_df[
                sido_df["선택_시군구"] == selected_sigungu
            ].copy()

            # --------------------------------------
            # 읍면동 선택
            # --------------------------------------

            dong_list = sorted(
                [
                    x
                    for x in sigungu_df["선택_읍면동"].unique()
                    if x and x != "nan"
                ]
            )

            selected_dong = st.selectbox(
                "③ 읍·면·동 선택",
                ["전체"] + dong_list
            )

            # --------------------------------------
            # 검색 버튼
            # --------------------------------------

            search_region = st.button(
                "🔍 선택 지역 인구 분포 검색",
                type="primary"
            )

            if search_region:

                result_df = sigungu_df.copy()

                if selected_dong != "전체":

                    result_df = result_df[
                        result_df["선택_읍면동"]
                        == selected_dong
                    ]

                if result_df.empty:

                    st.warning(
                        "선택한 지역의 인구 데이터를 "
                        "찾을 수 없습니다."
                    )

                else:

                    # ----------------------------------
                    # 연령별 인구 합산
                    # ----------------------------------

                    age_result = []

                    for age, age_col in age_columns:

                        population = pd.to_numeric(
                            result_df[age_col],
                            errors="coerce"
                        ).fillna(0).sum()

                        age_result.append({
                            "나이": f"{age}세",
                            "나이_숫자": age,
                            "인구수": int(population)
                        })

                    age_result_df = pd.DataFrame(
                        age_result
                    )

                    age_result_df = (
                        age_result_df
                        .sort_values("나이_숫자")
                        .reset_index(drop=True)
                    )

                    # ----------------------------------
                    # 지역 제목
                    # ----------------------------------

                    if selected_dong == "전체":

                        region_title = (
                            f"{selected_sido} "
                            f"{selected_sigungu}"
                        )

                    else:

                        region_title = (
                            f"{selected_sido} "
                            f"{selected_sigungu} "
                            f"{selected_dong}"
                        )

                    st.success(
                        f"선택 지역: {region_title}"
                    )

                    # ----------------------------------
                    # 총인구
                    # ----------------------------------

                    total_selected_population = (
                        age_result_df["인구수"].sum()
                    )

                    st.metric(
                        "선택 지역 총인구",
                        f"{total_selected_population:,}명"
                    )

                    # ----------------------------------
                    # 그래프
                    # ----------------------------------

                    st.subheader(
                        f"📈 {region_title} 연령별 인구 분포"
                    )

                    age_fig = px.bar(
                        age_result_df,
                        x="나이",
                        y="인구수",
                        labels={
                            "나이": "나이대",
                            "인구수": "인구수 (명)"
                        },
                        title=(
                            f"{region_title} "
                            "연령별 인구 분포"
                        )
                    )

                    age_fig.update_layout(
                        xaxis_title="나이대",
                        yaxis_title="인구수 (명)",
                        xaxis_tickangle=-45,
                        height=550
                    )

                    st.plotly_chart(
                        age_fig,
                        use_container_width=True
                    )

                    # ----------------------------------
                    # 표
                    # ----------------------------------

                    st.subheader(
                        "📋 연령별 인구 데이터"
                    )

                    table_df = age_result_df[
                        [
                            "나이",
                            "인구수"
                        ]
                    ].copy()

                    table_df["인구수"] = (
                        table_df["인구수"]
                        .map(lambda x: f"{x:,}명")
                    )

                    st.dataframe(
                        table_df,
                        use_container_width=True,
                        hide_index=True
                    )

# ==================================================
# 12. 기준 안내
# ==================================================

st.info(
    "현재 청년 비율 모드는 19~39세를 기준으로 계산합니다. "
    "청년 연령 기준은 분석 목적에 따라 변경할 수 있습니다."
)
