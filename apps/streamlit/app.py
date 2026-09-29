"""Seven-page, read-only SoD Access Intelligence dashboard."""

import streamlit as st

from apps.streamlit.theme import css

st.set_page_config(page_title="Governança de Acessos", layout="wide")
st.markdown(css(), unsafe_allow_html=True)
st.sidebar.title("Governança de Acessos")
st.sidebar.caption("Segurança, identidades e risco · POC V2")

pages = {
    "VISÃO DE NEGÓCIO": [
        st.Page("pages/executive_overview.py", title="01 Visão Executiva", default=True),
        st.Page("pages/access_business.py", title="02 Acessos"),
        st.Page("pages/risk_prioritization.py", title="03 Risco e Priorização"),
        st.Page("pages/explainability.py", title="04 Entenda a Decisão"),
    ],
    "ANÁLISE": [
        st.Page("pages/data_analysis.py", title="05 Análise de Dados"),
        st.Page("pages/poc_validation.py", title="06 Validação da POC V2"),
    ],
    "ENGENHARIA": [st.Page("pages/observability.py", title="07 Saúde dos Dados e do Pipeline")],
}
st.navigation(pages).run()
