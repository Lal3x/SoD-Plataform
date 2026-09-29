"""Executive view of persisted operational assessments."""

import streamlit as st

from apps.streamlit.components.charts import distribution
from apps.streamlit.components.layout import run_page, title
from apps.streamlit.components.metrics import count
from apps.streamlit.components.tables import policy_risk_matrix, show
from apps.streamlit.data.factory import gold


def render():
    title("Visão Executiva", "Acompanhe a situação geral dos acessos, os principais riscos e os casos que exigem atenção.")
    repo = gold()
    metrics = repo.get_executive_metrics()
    policy = {r["policy_decision"]: r["count"] for r in repo.get_policy_distribution()}
    cols = st.columns(5)
    for col, label, value in zip(cols, ("Acessos avaliados", "Padrão", "Legítimo", "Indevido", "Revisão"),
                                 (metrics["total"], policy.get("PADRAO", 0), policy.get("LEGITIMO", 0),
                                  policy.get("INDEVIDO", 0), policy.get("REVISAO", 0)), strict=True):
        with col:
            count(label, value)
    review_rate = (metrics["review"] / metrics["total"]) if metrics["total"] else 0
    st.markdown(f"A plataforma avaliou **{metrics['total']:,} acessos** e encaminhou casos que exigem análise humana."
                .replace(",", "."))
    st.caption("“Precisa de revisão” não significa acesso irregular. “Indevido” integra a fila de remediação.")
    cols = st.columns(4)
    risk = {r["risk_band"]: r["count"] for r in repo.get_risk_distribution()}
    for col, band in zip(cols, ("CRITICAL", "HIGH", "MEDIUM", "LOW"), strict=True):
        with col:
            count({"CRITICAL": "Risco crítico", "HIGH": "Risco alto", "MEDIUM": "Risco médio", "LOW": "Risco baixo"}[band], risk.get(band, 0))
    st.caption(f"Taxa de revisão: {review_rate:.2%}".replace(".", ","))
    st.subheader("Os nove pilares cobertos pela POC")
    st.caption("Resumo do escopo apresentado no case. São capacidades da solução, não uma nota de maturidade.")
    pillars = [
        ("1. Dados de origem", "Fontes de identidade, acesso e catálogo com rastreabilidade."),
        ("2. Qualidade dos dados", "Validação de integridade e tratamento de exceções."),
        ("3. Contexto de acesso", "Pessoa, permissão, sistema e contexto organizacional."),
        ("4. Padrão esperado", "Comparação explicável com grupos semelhantes."),
        ("5. Evidências", "Autorização, certificação, uso e tempo."),
        ("6. Decisão", "Classificação determinística e versionada."),
        ("7. Priorização", "Risco e ação recomendada, separados da decisão."),
        ("8. Resultado final", "Camada Gold para consumo e rastreabilidade."),
        ("9. Validação", "Avaliação offline com gabarito sintético."),
    ]
    for first, second, third in zip(pillars[::3], pillars[1::3], pillars[2::3], strict=True):
        for column, (heading, detail) in zip(st.columns(3), (first, second, third), strict=True):
            with column:
                st.markdown(f"**{heading}**\n\n{detail}")
    left, right = st.columns(2)
    with left:
        distribution(repo.get_policy_distribution(), "policy_decision", "Situação dos acessos")
    with right:
        distribution(repo.get_risk_distribution(), "risk_band", "Distribuição por nível de risco")
    st.subheader("Situação dos acessos por nível de risco")
    policy_risk_matrix(repo.get_policy_risk_matrix())
    st.subheader("O que merece atenção?")
    st.caption("Cada linha representa acessos, não pessoas. A comunidade apenas agrupa os resultados.")
    left, right = st.columns(2)
    with left:
        st.subheader("Comunidades com mais acessos indevidos")
        show([{"comunidade": row["identity_community"], "total_grants": row["total_grants"],
               "indevido": row["indevido"], "taxa_indevido": row["indevido_rate"]}
              for row in repo.get_community_analysis(sort_by="indevido")[:10]], height=320)
    with right:
        st.subheader("Comunidades com mais acessos para revisão")
        show([{"comunidade": row["identity_community"], "total_grants": row["total_grants"],
               "revisao": row["revisao"], "taxa_revisao": row["review_rate"]}
              for row in repo.get_community_analysis(sort_by="revisao")[:10]], height=320)


run_page(render)
