from datetime import datetime
from src.terminal_core.vessel import Vessel, VesselStatus
from src.terminal_core.exceptions import VesselValidationError
from src.terminal_core.berth import Berth, BerthOccupancy
from src.terminal_core.quay_crane import CraneStatus, QuayCrane
from src.terminal_core.yard_block import YardBlock, YardCapability

vessel1 = Vessel(
    vessel_id="V002",
    length_m=280.0,
    eta=datetime(2026, 8, 3, 14, 30),
    workload_moves=2200,
    priority=3,
    max_cranes=4,
)

vessel2 = Vessel(
    vessel_id="V003",
    length_m=315.5,
    eta=datetime(2026, 8, 3, 14, 30),
    workload_moves=2200,
    priority=3,
    max_cranes=4,
)

berth1 = Berth(
    berth_id="B01",
    length_m=1200.0,
    min_clearance_m=25.0,
)

crane1 = QuayCrane(
    crane_id="QC01",
    position_m=250.0,
    moves_per_hour=30.0,
)
crane2 = QuayCrane(
    crane_id="QC02",
    position_m=620.0,
    moves_per_hour=28.5,
)

block_r01 = YardBlock(
    block_id="R01",
    capacity_teu=600.0,
    capabilities={
        YardCapability.GENERAL,
        YardCapability.REEFER_POWER,
    },
)

block_r01.store_group(
    group_id="G001",
    teu=120.0,
    required_capabilities={
        YardCapability.GENERAL,
        YardCapability.REEFER_POWER,
    },
)

block_r01.reserve_capacity(
    group_id="G002",
    teu=80.0,
    required_capabilities={
        YardCapability.GENERAL,
    },
)

block_r01.save_to_json(
    "data/yard_block_r01.json"
)