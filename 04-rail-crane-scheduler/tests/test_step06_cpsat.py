import importlib.util
import pytest
from test_step02_contracts import fixture
from rail_crane_scheduler.cpsat import *


def test_tiny_exhaustive_reference():
    p=fixture(); paths,nodes=enumerate_paths(p,1000)
    assert paths and nodes<1000
    assert min(verify(p,s).makespan_min for s in paths)==5
    assert all(verify(p,s).valid_complete for s in paths)


def test_no_false_bound_on_budget_or_scaling():
    with pytest.raises(ContractError): enumerate_paths(fixture(),1)
    with pytest.raises(ContractError): exact_tick(1.2,1,1e-9)
    with pytest.raises(ContractError): exact_tick(1,float("nan"),1e-9)
    assert exact_tick(5,0.5,1e-9)==10


def test_dependency_or_real_solver_status():
    # Total budget now includes first Windows DLL import and path enumeration.
    result=solve(fixture(),tick_min=1.,wall_limit_s=10.,max_nodes=1000)
    if importlib.util.find_spec("ortools") is None:
        assert result.status=="DEPENDENCY_PENDING" and result.schedule is None and result.bound_min is None
    else:
        assert result.status=="OPTIMAL" and result.objective_min==result.bound_min==5


def test_actual_ortools_integration():
    pytest.importorskip("ortools",reason="OR-Tools must be installed in the isolated research environment")
    result=solve(fixture(),tick_min=1.,wall_limit_s=10.,max_nodes=1000)
    assert result.status=="OPTIMAL" and verify(fixture(),result.schedule).valid_complete
