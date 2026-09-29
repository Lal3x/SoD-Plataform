"""Great Expectations integration using in-memory Spark DataFrames."""

from __future__ import annotations

import json

import great_expectations as gx
from pyspark.sql import DataFrame


def validate_with_gx(
    name: str, dataframe: DataFrame, domains: dict[str, list[str]] | None = None
) -> list[dict]:
    """Run a compact table-specific GX suite and return serializable evidence."""
    name = {
        "identity_master": "identities",
        "iga_entitlements": "entitlements",
        "iga_access_assignments": "accesses",
        "iga_access_requests": "approvals",
    }.get(name, name)
    checks = {
        "identities": [
            gx.expectations.ExpectColumnValuesToNotBeNull(column="identidade_id"),
            gx.expectations.ExpectColumnValuesToNotBeNull(column="comunidade"),
            gx.expectations.ExpectColumnValuesToBeUnique(column="identidade_id"),
            gx.expectations.ExpectColumnValuesToBeInSet(
                column="tipo_identidade",
                value_set=(domains or {}).get("tipo_identidade", []),
            ),
            gx.expectations.ExpectColumnValuesToBeOfType(
                column="data_entrada_comunidade_atual", type_="DateType"
            ),
        ],
        "entitlements": [
            gx.expectations.ExpectColumnValuesToNotBeNull(column="entitlement_id"),
            gx.expectations.ExpectColumnValuesToBeUnique(column="entitlement_id"),
            gx.expectations.ExpectColumnValuesToNotBeNull(column="sigla_id"),
            gx.expectations.ExpectColumnValuesToNotBeNull(
                column="comunidade_dona_sigla"
            ),
            gx.expectations.ExpectColumnValuesToBeOfType(
                column="birthright", type_="BooleanType"
            ),
            gx.expectations.ExpectColumnValuesToBeOfType(
                column="sigla_publica", type_="BooleanType"
            ),
        ],
        "accesses": [
            gx.expectations.ExpectColumnValuesToNotBeNull(column="identidade_id"),
            gx.expectations.ExpectColumnValuesToNotBeNull(column="entitlement_id"),
            gx.expectations.ExpectColumnValuesToBeInSet(
                column="tipo_atribuicao",
                value_set=(domains or {}).get("tipo_atribuicao", []),
            ),
            gx.expectations.ExpectColumnValuesToBeOfType(
                column="data_concessao", type_="DateType"
            ),
            gx.expectations.ExpectColumnValuesToBeOfType(
                column="ultimo_uso", type_="DateType"
            ),
        ],
        "approvals": [
            gx.expectations.ExpectColumnValuesToNotBeNull(column="identidade_id"),
            gx.expectations.ExpectColumnValuesToNotBeNull(column="entitlement_id"),
            gx.expectations.ExpectColumnValuesToNotBeNull(column="aprovador"),
            gx.expectations.ExpectColumnValuesToBeOfType(
                column="data_aprovacao", type_="DateType"
            ),
        ],
    }
    checks.update(
        {
            "identity_directory": [
                gx.expectations.ExpectColumnValuesToNotBeNull(column="account_id"),
                gx.expectations.ExpectColumnValuesToBeInSet(
                    column="status_conta",
                    value_set=(domains or {}).get(
                        "status_conta", ["active", "disabled", "locked"]
                    ),
                ),
            ],
            "application_catalog": [
                gx.expectations.ExpectColumnValuesToNotBeNull(column="sigla_id"),
                gx.expectations.ExpectColumnValuesToBeUnique(column="sigla_id"),
            ],
            "access_certifications": [
                gx.expectations.ExpectColumnValuesToNotBeNull(column="campaign_id"),
                gx.expectations.ExpectColumnValuesToBeInSet(
                    column="decisao",
                    value_set=(domains or {}).get(
                        "decisao", ["MAINTAIN", "REVOKE", "PENDING"]
                    ),
                ),
            ],
        }
    )
    if name == "approvals" and "status_solicitacao" in dataframe.columns:
        checks[name] = [
            gx.expectations.ExpectColumnValuesToNotBeNull(column="request_id"),
            gx.expectations.ExpectColumnValuesToBeInSet(
                column="status_solicitacao",
                value_set=["APPROVED", "REJECTED", "PENDING"],
            ),
        ]
    context = gx.get_context(mode="ephemeral")
    source = context.data_sources.add_spark(name=f"silver_{name}")
    asset = source.add_dataframe_asset(name=f"{name}_data")
    batch_def = asset.add_batch_definition_whole_dataframe("whole_table")
    batch = batch_def.get_batch(batch_parameters={"dataframe": dataframe})
    results = []
    for expectation in checks[name]:
        result = batch.validate(expectation)
        results.append(
            {
                "expectation_type": expectation.__class__.__name__,
                "column": expectation.column,
                "success": bool(result.success),
                "result": json.dumps(
                    {
                        k: v
                        for k, v in result.result.items()
                        if k
                        in {
                            "element_count",
                            "unexpected_count",
                            "unexpected_percent",
                            "missing_count",
                        }
                    },
                    default=str,
                ),
            }
        )
    return results
