# Step 09 proposed RL interface

One centralized scheduler; rank-ordered crane slots, task slots sorted by stable
original task ID, padding mask, action 0 WAIT, action 1+rank*M+slot assignment.
Capacity overflow rejects, never truncates original work. Masks query the same
kernel oracle; bounded clone tests verify true accepts and false rejects at every
visited fixture state. No hidden future process exists in static v1; seed/scenario
identity perturbation changes neither observations nor masks.

EncodedCraneEnv has clock(1), cranes(2,7), tasks(M,5), task_mask(M), geometry(3).
Crane features: position, availability, remaining commitment, reach lower/upper,
speed and rate. Task features: bay position, remaining moves, ready, assigned,
completed. Geometry: clearance/span, orientation and hull length/span.
Float64 intermediate transforms precede float32 encoding. Scales derive only
from current known geometry/rates/workload; no test-fit statistics or clipping.
Padding stays zero with a separate mask. Unsupported range fails explicitly.

Reward = -elapsed_minutes / explicit_scale; undiscounted successful return is
-makespan/scale. Failure penalty -(H+margin)/scale makes incomplete outcomes worse
than any complete T<=H under undiscounted accounting. Gamma<1 changes this
equivalence; training config requires gamma=1 for this profile. No shaping/cargo
reward. PPO library timeout bootstrapping must be disabled for absorbing failure
truncations, not confused with an externally interrupted valid episode.

Interface lock is PENDING_OWNER_APPROVAL. The restricted action space has no joint
yield/reposition capability. Engineering tests do not approve a research reward,
physical profile or training budget, and do not create a trained policy.
