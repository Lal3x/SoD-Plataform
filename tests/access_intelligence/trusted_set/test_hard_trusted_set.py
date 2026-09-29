from datetime import date

import pytest
from pyspark.sql import functions as F

from sod_platform.access_intelligence.trusted_set.engine import build_hard_trusted_set


def _context(spark):
    return spark.createDataFrame(
        [
            ("same-private", True, False, False, None, False),
            ("not-anchor", False, False, False, None, False),
            ("cross-private", True, True, False, None, False),
            ("cross-public", True, True, True, None, False),
            ("public-revoked", True, True, True, "REVOKE", False),
            ("same-revoked", True, False, False, "REVOKE", False),
            ("blocking", True, False, False, None, True),
        ],
        "grant_id string, birthright boolean, cross_community boolean, sigla_publica boolean, certification_decisao string, data_quality_blocking boolean",
    ).withColumn("assessment_date", F.lit(date(2025, 2, 1)))


def test_hard_trusted_set_uses_birthright_as_explicit_anchor(spark):
    result = {r.grant_id: r for r in build_hard_trusted_set(_context(spark)).collect()}
    assert result["same-private"].hard_trusted_flag is True
    assert result["same-private"].hard_trusted_reason == "TRUSTED_BIRTHRIGHT_ANCHOR"
    assert result["not-anchor"].hard_trusted_reason == "EXCLUDED_NOT_EXPLICIT_ANCHOR"
    assert result["cross-private"].hard_trusted_reason == "EXCLUDED_CONTEXT_CONFLICT"
    assert result["cross-public"].hard_trusted_flag is True
    assert result["cross-public"].hard_trusted_reason == "TRUSTED_BIRTHRIGHT_ANCHOR"
    assert result["public-revoked"].hard_trusted_reason == "EXCLUDED_EXPLICIT_CONTRADICTION"
    assert result["same-revoked"].hard_trusted_reason == "EXCLUDED_EXPLICIT_CONTRADICTION"
    assert result["blocking"].hard_trusted_reason == "EXCLUDED_BLOCKING_DQ"
    assert {r.hard_trusted_rule_version for r in result.values()} == {"2.1.0"}


def test_hard_trusted_set_rejects_incomplete_context(spark):
    with pytest.raises(ValueError, match="birthright"):
        build_hard_trusted_set(spark.createDataFrame([("g",)], "grant_id string"))
