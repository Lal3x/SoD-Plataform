"""Brand and semantic tokens for the contextual POC."""

BRAND_ORANGE = "#EC7000"
BRAND_ORANGE_LIGHT = "#FF8C33"
BRAND_ORANGE_SOFT = "#FFD6A8"
BRAND_ORANGE_DARK = "#CC6000"
BRAND_BLUE = "#003399"
BRAND_BLUE_DARK = "#002266"
WHITE = "#FFFFFF"
BACKGROUND = "#F7F7F7"
SURFACE = WHITE
BORDER = "#EDEDED"
TEXT_PRIMARY = "#262323"
TEXT_SECONDARY = "#5A5555"
POLICY_COLORS = {
    "PADRAO": BRAND_BLUE,
    "LEGITIMO": "#167347",
    "REVISAO": "#A65C00",
    "INDEVIDO": "#B42318",
}
RISK_COLORS = {
    "LOW": "#167347",
    "MEDIUM": BRAND_BLUE,
    "HIGH": "#A65C00",
    "CRITICAL": "#B42318",
}


def css():
    return f"""<style>
    .stApp {{background:{BACKGROUND};color:{TEXT_PRIMARY}}}
    [data-testid='stSidebar'] {{background:{BRAND_BLUE_DARK}}}
    [data-testid='stSidebar'] * {{color:{WHITE}}}
    h1,h2,h3 {{color:{BRAND_BLUE_DARK}}}
    [data-testid='stMetric'] {{background:{SURFACE};border:1px solid {BORDER};
      border-left:4px solid {BRAND_ORANGE};padding:1rem;border-radius:8px;box-shadow:none}}
    [data-testid='stVerticalBlockBorderWrapper'] {{border-color:{BORDER};border-radius:8px}}
    [data-testid='stSidebarNav'] a[aria-current='page'] {{background:{BRAND_ORANGE};border-radius:6px}}
    .stCaption {{color:{TEXT_SECONDARY}}}
    .stButton button {{border-color:{BRAND_ORANGE};color:{BRAND_BLUE_DARK}}}
    </style>"""
