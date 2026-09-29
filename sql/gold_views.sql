-- Apply in a SQL catalog with persistent view support. The local Iceberg Hadoop
-- catalog used by this POC does not support CREATE VIEW.
CREATE VIEW sod.gold.remediation_queue AS
SELECT * FROM sod.gold.sod_assessment_gold001 WHERE policy_decision = 'INDEVIDO';

CREATE VIEW sod.gold.review_queue AS
SELECT * FROM sod.gold.sod_assessment_gold001 WHERE policy_decision = 'REVISAO';

CREATE VIEW sod.gold.executive_summary AS
SELECT policy_decision, risk_band, identity_community, sigla_id, privileged,
       regulatory_scope, COUNT(*) AS grant_count
FROM sod.gold.sod_assessment_gold001
GROUP BY policy_decision, risk_band, identity_community, sigla_id, privileged, regulatory_scope;
