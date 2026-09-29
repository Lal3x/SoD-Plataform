"""Business-first operational reliability view over persisted observations."""

import streamlit as st

from apps.streamlit.components.layout import run_page, title
from apps.streamlit.components.metrics import count
from apps.streamlit.components.tables import show
from apps.streamlit.data.factory import observability

RECONCILIATION_LABELS = {
    "policy_mismatch": "Decisões do acesso",
    "risk_mismatch": "Níveis de risco",
    "expected_access_mismatch": "Compatibilidade com o perfil",
    "evidence_mismatch": "Evidências do acesso",
}


def reconciliation_rows(reconciliation: dict) -> list[dict]:
    return [
        {
            "verificacao": RECONCILIATION_LABELS.get(key, key),
            "divergencias": value,
            "situacao": "Consistente" if value == 0 else "Requer investigação",
        }
        for key, value in reconciliation.items()
    ]


def render():
    title(
        "Saúde dos Dados e do Pipeline",
        "Acompanhe a confiabilidade dos dados que sustentam as decisões de acesso.",
    )
    repo = observability()
    reconciliation, counts = (
        repo.get_reconciliation_metrics(),
        repo.get_pipeline_counts(),
    )
    gold_count = next((row["count"] for row in counts if row["stage"] == "Gold"), None)
    rows = reconciliation_rows(reconciliation)
    divergences = sum(
        value for value in reconciliation.values() if isinstance(value, int)
    )
    if reconciliation and divergences == 0:
        st.success(
            "Resultado consistente: não foram encontradas divergências entre a camada final e suas saídas analíticas de suporte."
        )
    elif reconciliation:
        st.warning(
            "Há verificações que precisam de investigação. Consulte o quadro de consistência abaixo."
        )
    else:
        st.info(
            "As verificações de consistência ainda não estão disponíveis para este processamento."
        )
    metrics = (
        ("Acessos na camada final", gold_count),
        ("Decisões consistentes", reconciliation.get("policy_mismatch")),
        ("Riscos consistentes", reconciliation.get("risk_mismatch")),
        ("Perfis consistentes", reconciliation.get("expected_access_mismatch")),
        ("Evidências consistentes", reconciliation.get("evidence_mismatch")),
    )
    for column, (heading, value) in zip(st.columns(5), metrics, strict=True):
        with column:
            count(heading, value)
    overview, quality, audit = st.tabs(
        ["Visão operacional", "Qualidade dos dados", "Auditoria técnica"]
    )
    with overview:
        st.subheader("Como o resultado final é sustentado")
        st.caption(
            "Fluxo resumido das etapas materializadas. Detalhes técnicos ficam na aba de auditoria."
        )
        flow = [
            ("Dados de origem", "Acessos e referências recebidos."),
            ("Preparação", "Dados padronizados e contextualizados."),
            ("Inteligência de acesso", "Padrão esperado e evidências consolidados."),
            ("Decisão e prioridade", "Situação e risco calculados."),
            ("Resultado final", "Acessos publicados para consumo."),
        ]
        for column, (heading, description) in zip(st.columns(5), flow, strict=True):
            with column:
                st.markdown(f"**{heading}**\n\n{description}")
        left, right = st.columns(2)
        with left:
            st.subheader("Etapas materializadas")
            show(
                counts,
                height=360,
                legend="O que mostra: quantidade de registros disponíveis em cada etapa persistida do processamento.",
            )
        with right:
            st.subheader("Verificações de consistência")
            show(
                rows,
                height=360,
                legend="O que mostra: comparação da camada final com suas saídas de decisão, risco, perfil e evidências. Zero divergências significa resultado consistente.",
            )
    with quality:
        st.subheader("Qualidade e exceções dos dados")
        st.caption(
            "Problemas estruturais são acompanhados separadamente da análise de negócio."
        )
        quality_rows = repo.get_data_quality_metrics()
        if quality_rows:
            show(
                quality_rows,
                height=300,
                legend="O que mostra: registros agrupados pelo indicador de qualidade persistido.",
            )
        else:
            st.info("Não há métricas de qualidade disponíveis neste processamento.")
        st.subheader("Registros em quarentena")
        quarantine = repo.get_quarantine_metrics()
        if quarantine:
            show(
                quarantine,
                height=300,
                legend="O que mostra: registros isolados por falha estrutural ou de integridade para investigação.",
            )
        else:
            st.info("Não há registros de quarentena disponíveis.")
    with audit:
        st.subheader("Versões utilizadas")
        show(
            repo.get_versions(),
            height=180,
            legend="O que mostra: versões persistidas das saídas que compõem a camada final.",
        )
        with st.expander("Ver pipeline técnico"):
            st.code(
                "Raw → Bronze → Silver → Access Context → HTS → Observed Baseline → Hierarchical Fallback → Expected Access → Evidence → Policy → Risk → Gold"
            )
        with st.expander("Rastreabilidade dos dados"):
            st.json(repo.get_lineage())
        timestamp = repo.get_processing_timestamp()
        if timestamp is not None:
            st.caption(f"Último processamento da camada final: {timestamp}")


run_page(render)
