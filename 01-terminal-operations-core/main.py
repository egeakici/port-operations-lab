from datetime import datetime
from src.terminal_core.vessel import Vessel, VesselStatus
from src.terminal_core.exceptions import VesselValidationError


vessel1 = Vessel(
    vessel_id = "V001",
    length_m = 280.0,
    eta = datetime(2026, 8, 2, 9, 0),
    workload_moves = 1500,
    priority = 2,
    max_cranes = 3,
)

vessel2 = Vessel(
    vessel_id="V002",
    length_m=315.5,
    eta=datetime(2026, 8, 3, 14, 30),
    workload_moves=2200,
    priority=3,
    max_cranes=4,
)

vessel2.transition_to(VesselStatus.WAITING)

vessel2.save_to_json("data/vessel2.json")

loaded_vessel = Vessel.load_from_json("data/vessel2.json")

print("Original:", vessel2)
print("Loaded:", loaded_vessel)

print(type(loaded_vessel))
print(type(loaded_vessel.eta))
print(type(loaded_vessel.status))