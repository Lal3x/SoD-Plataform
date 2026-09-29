"""Offline validation area; the sole UI consumer of the validation mart."""

import streamlit as st

from apps.streamlit.components.layout import run_page, title
from apps.streamlit.components.metrics import count, percent
from apps.streamlit.components.tables import show
from apps.streamlit.data.factory import validation


def render():
    title("Qualidade da Solução", "Validação da POC V2")
    st.caption(
        "Esta página compara as decisões da solução com o gabarito sintético usado exclusivamente para avaliação da POC."
    )
    repo = validation()
    summary = repo.get_validation_summary()
    cols = st.columns(3)
    for col, label, key in zip(
        cols,
        ("Acessos avaliados", "Casos com gabarito", "Sem rótulo"),
        ("runtime_grants", "labeled_grants", "unlabeled_grants"),
        strict=True,
    ):
        with col:
            count(label, summary[key])
    cols = st.columns(4)
    for col, label, key in zip(
        cols,
        (
            "Acurácia exata",
            "Acurácia automatizada",
            "Taxa de automação",
            "Taxa de revisão",
        ),
        (
            "overall_exact_accuracy",
            "automated_decision_accuracy",
            "automation_rate",
            "review_rate",
        ),
        strict=True,
    ):
        with col:
            percent(label, summary[key])
    with st.expander("Ver métricas detalhadas"):
        st.subheader("Precisão, Recall e F1 por classificação")
        show(repo.get_class_metrics(), height=200)
        st.info(
            "O recall de Legítimo deve ser lido junto da fila de revisão; as abstenções não são ocultadas."
        )
    st.subheader("Matriz de confusão")
    show(repo.get_confusion_matrix(), height=260)
    left, right = st.columns(2)
    with left:
        count(
            "Acessos indevidos classificados como seguros",
            summary["critical_false_safe_count"],
        )
        count(
            "Acessos válidos classificados incorretamente como indevidos",
            summary["false_indevido_count"],
        )
    with right:
        percent(
            "Padrão identificado com frequência ≥ 0,90",
            summary["normal_identifiability_90"],
        )
        percent("Indevidos em risco crítico", summary["indevido_critical_risk_rate"])
    st.subheader("Cenários")
    show(repo.get_scenario_metrics(), height=420)


run_page(render)
