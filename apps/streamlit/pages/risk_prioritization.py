"""Separate remediation and human review queues."""

import streamlit as st

from apps.streamlit.components.filters import select_filters
from apps.streamlit.components.layout import run_page, title
from apps.streamlit.components.metrics import count
from apps.streamlit.components.tables import pagination, selected_grant_action, show
from apps.streamlit.data.factory import gold


def render():
    title("Risco e Priorização", "Veja quais acessos precisam ser tratados primeiro e quais casos exigem análise humana.")
    repo = gold()
    review, remediation = st.tabs(["Acessos que precisam de revisão humana", "Acessos para remediação"])
    with review:
        st.info("As evidências disponíveis não permitiram uma decisão definitiva. Esses casos seguem para análise humana.")
        filters = select_filters(repo, ["risk_band", "identity_community", "squad", "cargo",
                                        "sigla_id", "expected_access_state", "approval_evidence_status",
                                        "approval_match_strength",
                                        "certification_status", "policy_rule_id", "criticidade"], "review")
        total = repo.count_assessments({**filters, "policy_decision": "REVISAO"})
        count("Casos que precisam de revisão", total)
        offset = pagination(total, key="review")
        rows = repo.get_review_queue(filters, offset=offset)
        st.caption("Clique em uma linha para selecioná-la; a lista permanece nesta página.")
        selected = show(rows, columns=["identidade_id", "identity_community", "sigla_id", "entitlement_id",
                                       "policy_reason_code", "risk_band", "priority_action"], selection_key="review_grant")
        selected_grant_action(selected, key="review_grant")
        st.subheader("Onde a revisão humana é mais necessária?")
        show(repo.distribution("risk_band", {"policy_decision": "REVISAO"}), height=210)
        for field, heading in (("identity_community", "Revisões por comunidade"),
                               ("sigla_id", "Revisões por sistema"),
                               ("policy_rule_id", "Revisões por regra aplicada"),
                               ("expected_access_state", "Revisões por compatibilidade com o perfil")):
            st.subheader(heading)
            show(repo.get_review_analysis(field, limit=10), height=250)
    with remediation:
        st.info("Acessos classificados como indevidos, ordenados pela prioridade de risco.")
        total = repo.count_assessments({"policy_decision": "INDEVIDO"})
        count("Candidatos à remediação", total)
        offset = pagination(total, key="remediation")
        rows = repo.get_remediation_queue(offset=offset)
        st.caption("Clique em uma linha para selecioná-la; a lista permanece nesta página.")
        selected = show(rows, columns=["identidade_id", "identity_community", "sigla_id", "entitlement_id",
                                       "policy_reason_code", "risk_band", "priority_action"], selection_key="remediation_grant")
        selected_grant_action(selected, key="remediation_grant")


run_page(render)
