"""Foreground-only progress, explicit devices and cooperative episode boundaries."""
from contextlib import contextmanager
import platform
import signal
import sys
import threading
import os
import shutil


class ManualStop(RuntimeError):
    """An explicit owner interruption, never a failed scientific observation."""


def device_info(requested='cpu', *, torch_info=False):
    result = {'requested': requested, 'simulation_device': 'cpu',
              'cpu': platform.processor() or platform.machine(), 'cuda_available': None}
    if torch_info:
        import torch
        result.update(torch_version=torch.__version__, cuda_available=torch.cuda.is_available(),
                      cuda_runtime=torch.version.cuda)
        if result['cuda_available']:
            result['gpu'] = torch.cuda.get_device_name(0)
    return result


def require_torch_device(requested):
    if requested not in ('cpu', 'cuda'):
        raise ValueError('device must be explicit: cpu or cuda')
    info = device_info(requested, torch_info=True)
    if requested == 'cuda' and not info['cuda_available']:
        raise RuntimeError('CUDA explicitly requested but unavailable; no CPU fallback')
    return info


def progress_bar(total, *, initial=0, description, unit='episode', device='cpu', enabled=True):
    from tqdm import tqdm
    # Children write through logged pipes. Use the real console width supplied
    # by their foreground parent, and CR-only position0 (no cursor-up escapes).
    columns=int(os.environ.get('ITP_TQDM_COLUMNS') or shutil.get_terminal_size().columns)
    return tqdm(total=total, initial=initial, desc=description, unit=unit, disable=not enabled,
                ncols=max(10,min(columns-1,160)), dynamic_ncols=False,
                ascii=True, mininterval=1.0,
                postfix={'model': device, 'sim': 'CPU'}, file=sys.stderr,
                position=0)


@contextmanager
def finish_current_episode_on_interrupt():
    """First Ctrl+C requests a boundary stop; second leaves an inspectable partial run."""
    requested = threading.Event()
    previous = signal.getsignal(signal.SIGINT)
    def interrupt(signum, frame):
        if requested.is_set():
            raise KeyboardInterrupt
        requested.set()
        print('\nStop requested: finishing and sealing the current episode. '
              'A second Ctrl+C interrupts immediately and requires partial-run inspection.', file=sys.stderr)
    signal.signal(signal.SIGINT, interrupt)
    try:
        yield requested
    finally:
        signal.signal(signal.SIGINT, previous)
