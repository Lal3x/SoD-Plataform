"""Portuguese-first presentation vocabulary for the Streamlit application.

Persistent values stay untouched in repositories.  This module translates them
only at the UI boundary, keeping technical codes available in drill-downs.
"""

FIELD_LABELS = {
    "identidade_id": "Identidade", "identity_community": "Comunidade", "squad": "Squad",
    "cargo": "Cargo", "identity_type": "Tipo de identidade", "manager": "Gestor",
    "sigla_id": "Sistema", "entitlement_id": "Permissão", "owner_community": "Comunidade responsável",
    "community_relation": "Relação entre comunidades", "policy_decision": "Situação do acesso",
    "risk_score": "Pontuação de risco", "risk_band": "Nível de risco",
    "priority_action": "Ação recomendada", "expected_access_state": "Compatibilidade com o perfil",
    "approval_evidence_status": "Evidência de autorização", "certification_status": "Situação da certificação",
    "selected_baseline_level": "Grupo de comparação utilizado", "population_size": "Pessoas comparáveis",
    "support_count": "Pessoas do grupo que possuem esse acesso", "prevalence": "Frequência no grupo",
    "policy_rule_id": "Regra aplicada", "decision_confidence": "Confiança da decisão",
    "data_concessao": "Data da concessão", "ultimo_uso": "Último uso", "sigla_publica": "Sistema público",
    "birthright": "Acesso padrão de função", "grant_id": "Identificador técnico do acesso",
    "assessment_date": "Data da avaliação", "dataset_version": "Versão do conjunto de dados",
}

VALUE_LABELS = {
    "PADRAO": "Padrão", "LEGITIMO": "Legítimo", "INDEVIDO": "Indevido", "REVISAO": "Precisa de revisão",
    "EXPECTED": "Compatível com o perfil", "UNEXPECTED": "Fora do padrão observado",
    "INSUFFICIENT_EVIDENCE": "Dados insuficientes", "LOW": "Baixo", "MEDIUM": "Médio",
    "HIGH": "Alto", "CRITICAL": "Crítico", "STRONG_INFERRED": "Forte evidência de autorização",
    "APPROVAL_NOT_FOUND": "Autorização não localizada",
    "CERTIFICATION_NOT_FOUND": "Certificação não localizada", "UNKNOWN": "Não informado",
}

POLICY_DESCRIPTIONS = {
    "PADRAO": "Acesso compatível com o padrão esperado para esse contexto.",
    "LEGITIMO": "Exceção justificada pelas evidências disponíveis.",
    "INDEVIDO": "Acesso sem justificativa válida encontrada segundo as regras avaliadas.",
    "REVISAO": "Evidências insuficientes ou conflitantes; recomenda-se análise humana.",
}


def label(value: object) -> object:
    """Return a friendly UI value while retaining unknown technical values."""
    return VALUE_LABELS.get(str(value), value) if value is not None else "Não informado"


def field_label(field: str) -> str:
    return FIELD_LABELS.get(field, field.replace("_", " ").capitalize())
