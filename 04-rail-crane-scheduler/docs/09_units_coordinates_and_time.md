# Units, frame and time

Authoritative elapsed time is minutes from planning start, wall computation is
seconds, rail/bay distances are meters, workload is integer moves, effective
crane rate is moves/hour. TEU and individual container counts are never inferred.
The exact unit tuple is `(min,m,moves,moves/hour)`.

Local bay offset u is measured from a named ship reference: positive orientation
maps to berth_origin+u; reverse orientation to berth_origin+length-u. Both are
tested. Missing transform, inconsistent supplied global position and out-of-hull
local position fail. Crane tuple order is physical rank 0,1, independent of IDs.

Optional epoch must be timezone-aware ISO8601. `planning_start_min` and later
schedule timestamps are elapsed numeric minutes in the same frame. There is one
execution clock. Contract validation does not advance it or calculate durations.
`moves_per_minute` is a pure unit conversion, not a productivity model.

Separation, tolerance, horizon, speed, rate and stationary setup have no numeric
production defaults. Null differs from zero. The proposed profile uses constant
speed, no acceleration model and reference-point clearance, not crane-body
certification. Numeric tolerances never authorize crossing or work loss.
