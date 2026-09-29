"""Boundary and repository checks for the read-only dashboard."""

from pathlib import Path

import pytest

from apps.streamlit.components.status import POLICY_HELP
from apps.streamlit.components.tables import display_value, present
from apps.streamlit.config import DATASET_VERSION, GOLD_TABLE, VALIDATION_TABLES
from apps.streamlit.data.base import ContractError, SparkSource
from apps.streamlit.data.cache import cached_gold_query
from apps.streamlit.data.gold_repository import GoldRepository
from apps.streamlit.data.validation_repository import ValidationRepository
from apps.streamlit.labels import FIELD_LABELS, POLICY_DESCRIPTIONS, label
from apps.streamlit.theme import (
    BRAND_BLUE_DARK,
    BRAND_ORANGE,
    POLICY_COLORS,
    RISK_COLORS,
    css,
)

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/streamlit"


def test_seven_pages_exist():
    assert (
        len(list((APP / "pages").glob("*.py"))) == 8
    )  # seven pages and package marker


def test_v2_contract_and_runtime_isolation():
    assert DATASET_VERSION == "V2"
    assert GOLD_TABLE.startswith("sod.gold.")
    assert all(
        table.startswith("sod.validation.") for table in VALIDATION_TABLES.values()
    )
    for name in (
        "executive_overview",
        "access_business",
        "risk_prioritization",
        "explainability",
        "data_analysis",
        "observability",
    ):
        page = (APP / "pages" / f"{name}.py").read_text()
        assert "ValidationRepository" not in page
        assert "sod.validation" not in page
        assert "ground_truth" not in page
        assert "spark.sql(" not in page


def test_no_legacy_dataset_dependency():
    for path in APP.rglob("*.py"):
        body = path.read_text().lower()
        assert "dataset_v1" not in body
        assert "ground_truth_v1" not in body
        assert "v1_v2_comparison" not in body
        assert "peer_discovery" not in body


def test_gold_search_rejects_invalid_pagination():
    repo = GoldRepository(SparkSource(object()))
    with pytest.raises(ValueError):
        repo.search_assessments(limit=0)
    with pytest.raises(ValueError):
        repo.search_assessments(offset=-1)


def test_validation_methods_are_offline_only():
    assert "get_validation_summary" in dir(ValidationRepository)
    assert "get_validation_summary" not in dir(GoldRepository)


def test_contract_error_is_explicit():
    assert issubclass(ContractError, RuntimeError)


def test_visual_statuses_keep_review_distinct_from_violation():
    assert len(set(POLICY_COLORS.values())) == 4
    assert len(set(RISK_COLORS.values())) == 4
    assert POLICY_COLORS["REVISAO"] != POLICY_COLORS["INDEVIDO"]
    assert "análise humana" in POLICY_HELP["REVISAO"]
    assert BRAND_ORANGE in css() and BRAND_BLUE_DARK in css()


def test_portuguese_first_labels_keep_technical_values_at_the_boundary():
    assert FIELD_LABELS["policy_decision"] == "Situação do acesso"
    assert label("REVISAO") == "Precisa de revisão"
    assert label("STRONG_INFERRED") == "Forte evidência de autorização"
    assert "análise humana" in POLICY_DESCRIPTIONS["REVISAO"]


def test_business_navigation_and_technical_disclosure_are_present():
    app = (APP / "app.py").read_text()
    detail = (APP / "pages/explainability.py").read_text()
    assert "Entenda a Decisão" in app
    assert "Saúde dos Dados e do Pipeline" in app
    assert "Detalhes técnicos e auditoria" in detail
    assert "Ver evidências detalhadas" in detail


def test_access_selection_keeps_pagination_before_opening_detail():
    page = (APP / "pages/access_business.py").read_text()
    table_component = (APP / "components/tables.py").read_text()
    assert "pagination" in page
    assert "selected_grant_action" in page
    assert "Entender a decisão deste acesso" in table_component


def test_explicit_pagination_reports_visible_range_and_total():
    table_component = (APP / "components/tables.py").read_text()
    assert "Exibindo acessos" in table_component
    assert "Página {current} de {pages}" in table_component


def test_table_presentation_normalizes_mixed_values_before_arrow_conversion():
    rendered = present([{"flag": True, "missing": None, "score": 1.5}])
    assert rendered == [{"Flag": "Sim", "Missing": "Não informado", "Score": "1,50"}]
    assert display_value(False) == "Não"


def test_dashboard_contains_no_data_mutation():
    forbidden = (
        "writeTo(",
        "createOrReplace(",
        "INSERT INTO",
        "DELETE FROM",
        "MERGE INTO",
    )
    for path in APP.rglob("*.py"):
        assert all(token not in path.read_text() for token in forbidden)


def test_cached_results_change_with_snapshot():
    class Query:
        def __init__(self):
            self.snapshot = "snapshot-a"
            self.calls = 0

        def snapshot_token(self):
            return self.snapshot

        @cached_gold_query()
        def result(self, value):
            self.calls += 1
            return value

    query = Query()
    assert query.result(7) == query.result(7) == 7
    assert query.calls == 1
    query.snapshot = "snapshot-b"
    assert query.result(7) == 7
    assert query.calls == 2


def test_cache_keeps_distinct_repository_methods_separate():
    class Query:
        def snapshot_token(self):
            return "same-snapshot"

        @cached_gold_query()
        def metrics(self):
            return {"total": 75577}

        @cached_gold_query()
        def matrix(self):
            return [{"policy_decision": "REVISAO", "risk_band": "HIGH", "count": 900}]

    query = Query()
    assert query.metrics() == {"total": 75577}
    assert query.matrix() == [
        {"policy_decision": "REVISAO", "risk_band": "HIGH", "count": 900}
    ]
