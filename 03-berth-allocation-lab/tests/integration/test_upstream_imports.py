from __future__ import annotations


def test_upstream_packages_import() -> None:
    from mini_port_sim import PortSimulation
    from mini_port_sim.scenario import ScenarioConfig
    from terminal_core import Berth, Terminal, Vessel

    assert Berth.__name__ == "Berth"
    assert Terminal.__name__ == "Terminal"
    assert Vessel.__name__ == "Vessel"
    assert PortSimulation.__name__ == "PortSimulation"
    assert ScenarioConfig.__name__ == "ScenarioConfig"

