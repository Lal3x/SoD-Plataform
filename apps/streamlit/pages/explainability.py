"""Business-first explanation of one persisted Gold assessment."""

import streamlit as st

from apps.streamlit.components.layout import run_page, title
from apps.streamlit.components.tables import show
from apps.streamlit.data.factory import gold
from apps.streamlit.labels import POLICY_DESCRIPTIONS, field_label, label


def facts(grant: dict, fields: list[str]) -> list[dict]:
    return [{"Informação": field_label(field), "Valor": label(grant[field])}
            for field in fields if field in grant]


def render():
    title("Entenda a Decisão", "Veja passo a passo por que um acesso recebeu determinada classificação e nível de risco.")
    repo = gold()
    grant_id = st.text_input("Identificador técnico do acesso", value=st.session_state.get("selected_grant", ""))
    if not grant_id:
        st.info("Informe um identificador técnico ou selecione um acesso nas páginas Acessos ou Risco e Priorização.")
        return
    grant = repo.get_grant(grant_id)
    if grant is None:
        st.warning("Acesso não encontrado na camada final.")
        return
    st.caption(f"Avaliado em {grant.get('assessment_date')} · Conjunto de dados {grant.get('dataset_version')}")
    left, right = st.columns(2)
    with left:
        st.subheader("Decisão do acesso")
        decision = grant.get("policy_decision")
        st.metric("Situação", label(decision))
        st.caption(POLICY_DESCRIPTIONS.get(decision, "Decisão registrada na camada final."))
    with right:
        st.subheader("Nível de risco")
        st.metric("Prioridade de tratamento", label(grant.get("risk_band")))
        st.caption("O risco define a prioridade de tratamento e não altera a classificação do acesso.")
    st.subheader("Quem é a pessoa?")
    show(facts(grant, ["identity_community", "squad", "cargo", "identity_type", "manager"]), height=210)
    st.subheader("Qual acesso ela possui?")
    show(facts(grant, ["sigla_id", "entitlement_id", "owner_community", "community_relation", "sigla_publica", "birthright", "data_concessao", "ultimo_uso"]), height=240)
    st.subheader("Esse acesso combina com o perfil?")
    st.metric("Compatibilidade com o perfil", label(grant.get("expected_access_state")))
    with st.expander("Como isso foi determinado?"):
        show(facts(grant, ["selected_baseline_level", "population_size", "support_count", "prevalence", "expected_access_strength", "expected_access_reason_code"]), height=260)
    st.subheader("Evidências do acesso")
    show(facts(grant, ["approval_evidence_status", "approval_match_strength", "certification_status", "usage_status", "data_quality_blocking", "grant_temporal_status"]), height=250)
    with st.expander("Ver evidências detalhadas"):
        if st.button("Carregar evidências", key="load_facts"):
            show(repo.get_grant_evidence(grant_id), height=460)
    with st.expander("Detalhes técnicos e auditoria"):
        show(facts(grant, ["grant_id", "assessment_date", "policy_rule_id", "policy_reason_code", "decision_confidence", "policy_version", "risk_score", "risk_driver_1", "risk_driver_2", "risk_driver_3", "risk_version", "dataset_version"]), height=420)


run_page(render)
