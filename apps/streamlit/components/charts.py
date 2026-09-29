"""Charts for already computed counts."""

import altair as alt
import pandas as pd
import streamlit as st

from apps.streamlit.labels import field_label, label
from apps.streamlit.theme import BRAND_BLUE, POLICY_COLORS, RISK_COLORS

CHART_LEGENDS = {
    "policy_decision": "O que mostra: a quantidade de acessos em cada situação. “Precisa de revisão” representa incerteza ou conflito de evidências, não uma irregularidade confirmada.",
    "risk_band": "O que mostra: a quantidade de acessos por prioridade de tratamento. O nível de risco não muda a situação do acesso.",
    "expected_access_state": "O que mostra: se o acesso é compatível com o perfil observado de pessoas em contexto semelhante.",
    "prevalence_band": "O que mostra: a frequência observada do acesso em grupos comparáveis. Frequência é evidência de padrão, não autorização por si só.",
}


def distribution(rows: list[dict], dimension: str, title: str):
    st.subheader(title)
    st.caption(CHART_LEGENDS.get(dimension, "O que mostra: a distribuição dos acessos pela dimensão selecionada."))
    if not rows:
        st.info("Nenhum registro disponível.")
        return
    frame = pd.DataFrame(rows)
    frame[dimension] = frame[dimension].fillna("UNKNOWN").astype(str)
    palette = (POLICY_COLORS if dimension == "policy_decision" else
               RISK_COLORS if dimension == "risk_band" else None)
    if palette:
        color = alt.Color(dimension, scale=alt.Scale(domain=list(palette), range=list(palette.values())),
                          legend=None)
    else:
        color = alt.value(BRAND_BLUE)
    frame[f"{dimension}_label"] = frame[dimension].map(label)
    chart = alt.Chart(frame).mark_bar().encode(
        x=alt.X(f"{dimension}_label:N", sort="-y", title=None),
        y=alt.Y("count:Q", title="Acessos"),
        color=color,
        tooltip=[alt.Tooltip(f"{dimension}_label:N", title=field_label(dimension)), "count:Q"],
    )
    st.altair_chart(chart, width="stretch")
