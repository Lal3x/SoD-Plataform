# Deterministic test fixtures

Fixtures are deliberately small, versioned test inputs. They are never runtime
inputs and must not be used for baseline construction or policy calibration.

`silver/access_scenarios.json` is a compact domain matrix for expected access,
birthright, service identity, approved and unapproved exceptions, sensitive
access, and review cases. It deliberately describes expected test outcomes
without becoming an input to the production pipeline.
