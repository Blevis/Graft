# extract_v2 prompt / extract_v3 schema: tuned for small local models (one fact per claim; reference null unless access,
# enforced by the schema). Measured in docs/eval.md.
PROMPT_VERSION = "extract_v2"
SCHEMA_VERSION = "extract_v3"
# Recorded examples were written against the v1 contract (AGENT_SPEC.md); they keep that label when replayed.
REPLAY_PROMPT_VERSION = "extract_v1"
REPLAY_SCHEMA_VERSION = "extract_v1"
SUGGEST_PROMPT_VERSION = "suggest_v1"
REPLAY_MODEL = "fixture:agent-spec-v1"  # committed example responses, labelled "Recorded example" in the UI
