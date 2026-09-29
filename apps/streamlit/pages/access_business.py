"""Filtered access population with bounded pages."""

import streamlit as st

from apps.streamlit.components.filters import select_filters
from apps.streamlit.components.layout import run_page, title
from apps.streamlit.components.metrics import count
from apps.streamlit.components.tables import pagination, selected_grant_action, show
from apps.streamlit.data.factory import gold


def render():
    title("Acessos", "Pesquise pessoas, sistemas e permissões e veja como cada acesso foi avaliado.")
    repo = gold()
    search = st.text_input("Buscar identidade, sistema, permissão ou identificador técnico")
    with st.expander("Filtros", expanded=True):
        filters = select_filters(repo, ["identity_community", "squad", "cargo", "identity_type",
                                        "sigla_id", "entitlement_id", "policy_decision", "risk_band",
                                        "expected_access_state", "privileged", "regulatory_scope",
                                        "sigla_publica", "birthright"], "access")
    total = repo.count_assessments(filters, search)
    count("Acessos encontrados", total)
    offset = pagination(total, key="access")
    rows = repo.search_assessments(filters, search, offset=offset)
    st.caption("A situação classifica o acesso. O nível de risco indica a prioridade de tratamento.")
    st.caption("Clique em uma linha para selecioná-la. A paginação e os filtros permanecem nesta página.")
    selected = show(rows, columns=["identidade_id", "identity_community", "sigla_id", "entitlement_id",
                                   "expected_access_state", "policy_decision", "risk_band", "priority_action"],
                    selection_key="access_grant")
    selected_grant_action(selected, key="access_grant")


run_page(render)
