"""Descriptive analysis of upstream results only."""

import streamlit as st

from apps.streamlit.components.charts import distribution
from apps.streamlit.components.layout import run_page, title
from apps.streamlit.components.tables import show
from apps.streamlit.data.factory import gold


def render():
    title(
        "Análise de Dados",
        "Explore como os acessos estão distribuídos entre comunidades, sistemas, perfis e tipos de decisão.",
    )
    repo = gold()
    tab_names = [
        "Comunidades",
        "Sistemas",
        "Permissões",
        "Compatibilidade com o perfil",
        "Evidências",
        "Revisões",
    ]
    tabs = st.tabs(tab_names)
    with tabs[0]:
        show(repo.get_community_analysis())
    with tabs[1]:
        show(repo.get_application_analysis())
    with tabs[2]:
        show(repo.get_entitlement_analysis())
    with tabs[3]:
        st.caption(
            "Veja onde os acessos seguem ou fogem do padrão observado para pessoas com contexto semelhante."
        )
        distribution(
            repo.get_expected_access_analysis(),
            "expected_access_state",
            "Compatibilidade com o perfil",
        )
        with st.expander("Ver dados do padrão observado"):
            distribution(
                repo.get_prevalence_distribution(),
                "prevalence_band",
                "Frequência observada por faixa",
            )
            st.subheader("Grupo de comparação utilizado")
            show(repo.get_baseline_analysis(), height=300)
    with tabs[4]:
        for field, label in (
            ("approval_evidence_status", "Aprovação"),
            ("approval_match_strength", "Força do vínculo"),
            ("certification_status", "Certificação"),
            ("community_relation", "Relação comunitária"),
            ("birthright", "Acesso padrão de função"),
        ):
            distribution(repo.distribution(field), field, label)
    with tabs[5]:
        for field in (
            "identity_community",
            "sigla_id",
            "cargo",
            "expected_access_state",
            "approval_evidence_status",
            "certification_status",
            "risk_band",
        ):
            st.subheader(f"Revisão por {field.replace('_', ' ')}")
            show(repo.get_review_analysis(field), height=300)


run_page(render)
