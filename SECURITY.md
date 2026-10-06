# Security and data handling

ShapeWitness reads potentially untrusted JSONL locally. It does not evaluate input,
load plugins, make network calls, or execute commands derived from data. It uses
strict parsing and explicit resource limits. Limits are not an OS security sandbox;
use container/process/disk quotas for hostile inputs and dedicated scratch storage
where appropriate. Python and SQLite must receive normal security updates.

Selected rows retain every original value. Reports include key names, structure,
provenance, and hashes. Neither artifact is safe to publish merely because the input
has been reduced. Temporary deletion is not secure erasure. See the README for
scratch-storage and output-failure semantics.

For a suspected vulnerability, use GitHub's private vulnerability-reporting option
on this repository if it is available. Otherwise open an issue requesting a private
contact route without including exploit details, secrets, or private input data.
Do not assume a private reporting channel has been configured. No response-time or
support guarantee is implied for this initial release.
