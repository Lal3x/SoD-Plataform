"""Bounded tables and grant navigation."""

from datetime import date, datetime

import pandas as pd
import streamlit as st

from apps.streamlit.labels import field_label, label

BUSINESS_LEGENDS = {
    "identidade_id": "O que mostra: os acessos individuais encontrados. Use esta lista para localizar uma pessoa, sistema ou permissão e abrir sua análise.",
    "identity_community": "O que mostra: como os acessos se distribuem entre comunidades. Compare volume, exceções e necessidade de revisão para identificar onde atuar.",
    "sigla_id": "O que mostra: como os acessos se distribuem entre sistemas. Ajuda a identificar sistemas com maior concentração de risco ou revisão.",
    "entitlement_id": "O que mostra: permissões e a população que as possui. Use para identificar permissões mais recorrentes ou com mais exceções.",
    "risk_band": "O que mostra: quantidade de acessos por nível de risco. O risco orienta a ordem de tratamento; não altera a situação do acesso.",
    "ground_truth": "O que mostra: comparação entre a classificação esperada no gabarito sintético e a classificação produzida pela POC.",
    "stage": "O que mostra: quantos registros chegaram a cada etapa materializada do processamento.",
    "check": "O que mostra: verificações de consistência entre a camada final e as saídas analíticas que a sustentam. Zero indica ausência de divergência.",
}


def pagination(total: int, *, key: str, page_size: int = 50) -> int:
    """Show an explicit, bounded pager and return the result offset."""
    if total <= 0:
        return 0
    pages = max(1, (total + page_size - 1) // page_size)
    current = st.number_input(
        "Página", min_value=1, max_value=pages, value=1, step=1, key=f"{key}_page"
    )
    start = (current - 1) * page_size + 1
    end = min(current * page_size, total)
    st.caption(
        f"Exibindo acessos {start:,}–{end:,} de {total:,}. Página {current} de {pages}.".replace(
            ",", "."
        )
    )
    return (current - 1) * page_size


def present(rows: list[dict], columns: list[str] | None = None) -> list[dict]:
    """Translate to Arrow-safe display values at the presentation boundary."""
    output = []
    for row in rows:
        selected = ((key, row.get(key)) for key in (columns or list(row)))
        output.append(
            {field_label(key): display_value(value) for key, value in selected}
        )
    return output


def display_value(value: object) -> str:
    """Avoid mixed Python types in a visible dataframe before Arrow conversion."""
    friendly = label(value)
    if isinstance(friendly, bool):
        return "Sim" if friendly else "Não"
    if isinstance(friendly, (datetime, date)):
        return friendly.strftime("%d/%m/%Y")
    if isinstance(friendly, float):
        return f"{friendly:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if isinstance(friendly, int):
        return f"{friendly:,}".replace(",", ".")
    return str(friendly)


def show(
    rows: list[dict],
    *,
    height: int = 420,
    columns: list[str] | None = None,
    selection_key: str | None = None,
    legend: str | None = None,
) -> dict | None:
    """Render a table and optionally return its selected persisted record."""
    if not rows:
        st.info("Nenhum registro para os filtros selecionados.")
        return None
    visible_fields = columns or list(rows[0])
    st.caption(
        legend
        or BUSINESS_LEGENDS.get(
            visible_fields[0],
            "O que mostra: registros disponíveis para investigação. Cada linha representa um item do resultado apresentado.",
        )
    )
    options = {"width": "stretch", "hide_index": True, "height": height}
    if selection_key:
        options.update(
            on_select="rerun", selection_mode="single-row", key=selection_key
        )
    event = st.dataframe(pd.DataFrame(present(rows, columns)), **options)
    if selection_key and event.selection.rows:
        return rows[event.selection.rows[0]]
    return None


def policy_risk_matrix(rows: list[dict]):
    """Display persisted joint counts as a compact static cross-tab."""
    if not rows:
        st.info("Nenhum registro para a matriz Policy × Risk.")
        return
    st.caption(
        "Legenda: linhas mostram a situação do acesso; colunas mostram o nível de risco; cada célula é a quantidade de acessos."
    )
    frame = pd.DataFrame(rows)
    matrix = frame.pivot(index="policy_decision", columns="risk_band", values="count")
    matrix = matrix.reindex(
        index=["PADRAO", "LEGITIMO", "REVISAO", "INDEVIDO"],
        columns=["LOW", "MEDIUM", "HIGH", "CRITICAL"],
    )
    matrix.index = [label(value) for value in matrix.index]
    matrix.columns = [label(value) for value in matrix.columns]
    st.table(matrix.fillna(0).astype(int))


def selected_grant_action(row: dict | None, *, key: str):
    """Keep the selected case visible before deliberately opening its detail."""
    if not row or not row.get("grant_id"):
        return
    st.info(f"Acesso selecionado: {row['grant_id']}")
    if st.button("Entender a decisão deste acesso", key=f"open_{key}"):
        st.session_state["selected_grant"] = row["grant_id"]
        st.switch_page("pages/explainability.py")
