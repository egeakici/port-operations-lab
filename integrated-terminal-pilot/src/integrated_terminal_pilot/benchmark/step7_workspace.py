"""Source-defined portable execution context; never grants scientific permission."""
from pathlib import Path
from integrated_terminal_pilot.benchmark import step7 as s
from integrated_terminal_pilot.scenarios.config import load_generator_config as base_config

DEFAULT_BUNDLE = s.PROJECT_ROOT/'experiments/step7_remote/campaign_v1'


def bundle_path(path):
    p = Path(path).resolve()
    root = (s.PROJECT_ROOT/'experiments/step7_remote').resolve()
    if p == root or not p.is_relative_to(root):
        raise s.CampaignError('bundle must be a child of integrated-terminal-pilot/experiments/step7_remote')
    return p


def configure(path):
    """Keep canonical Step2 records unchanged; bind the exact approved copied register.

    A path is not authorization: require_owner, clean source, complete regression,
    real exclusive lock, source/checkpoint and split gates still all apply.
    """
    root = bundle_path(path)
    s.ROOT = root
    s.APPROVAL = root/'inputs/step7_owner_28_approval.json'
    s.FORMAL_LOCK_PATH = root/'protocol_lock_v1.json'
    def effective_config():
        register = root/'inputs/approved_generator_decisions.yaml'
        return base_config(decisions_path=register) if register.exists() else base_config()
    s.load_generator_config = effective_config
    s.PORTABLE_BUNDLE = root
    return root
