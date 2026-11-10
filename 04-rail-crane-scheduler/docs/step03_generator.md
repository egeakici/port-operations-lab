# Step 03 generator

`p04_counter_sha256_v2` uses counter SHA256 with rejection sampling for unbiased
integer draws. Named geometry/workload/positions/release streams derive from
namespace, seed, name and explicit nonce; workload draws cannot alter geometry.
V1 release stream is reserved, not a hidden dynamic-release implementation.

GeneratorConfig contains a complete explicit QCSPProblem template and task count,
move range, jitter and stream nonces. There are no numeric scientific defaults.
The final audit version adds required operation_kind and rejects the earlier v1
draft rather than guessing discharge. Earlier v1 test receipts remain unchanged.
All generated cases remain TEST_FIXTURE_SYNTHETIC. Only development/diagnostic
fixture roles execute automatically; primary generation remains PARAMETERS_PENDING.
The separate generate-manual command checks exact owner/source/config approval
before producing locked train/validation/test inputs; it was not run in development.
Scenario metadata alone cannot unlock generation. Families
are named but no family counts/distributions are approved. Dynamic diagnostics
are rejected as a deferred model. Zero jobs are correctness cases, not performance.

Physical hashes strip metadata to catch relabelled split duplicates. Generation
never schedules tasks. New output directories use exclusive writes and cannot
overwrite prior fixtures. Manifests record config/input hashes and seed roles.
Pure source inspection is separate from held-out data. CLI support is added in
the later common command layer; the generator API and fixture writer are usable
now and tested without producing scientific datasets.
