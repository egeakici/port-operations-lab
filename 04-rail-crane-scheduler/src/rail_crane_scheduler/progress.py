"""Real completed-work counters; stderr-only tqdm and append-only recovery log."""
import json
import sys
import time
from pathlib import Path
from tqdm import tqdm


class Progress:
    def __init__(self, total, description, directory=None, *, initial=0, unit="case"):
        self.total = total
        self.completed = initial
        self.started = time.monotonic()
        self.directory = Path(directory) if directory is not None else None
        self.bar = tqdm(total=total, initial=initial, desc=description, unit=unit,
                        file=sys.stderr, ascii=True, dynamic_ncols=True, mininterval=.5)
        self.fields = {}

    def record(self, event, **fields):
        self.fields.update(fields)
        row = {"event": event, "completed": self.completed, "total": self.total,
               "elapsed_s": time.monotonic()-self.started, **self.fields}
        if self.directory is not None:
            self.directory.mkdir(parents=True, exist_ok=True)
            with (self.directory/"progress.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, allow_nan=False)+"\n")
        # Keep paths and large validation payloads in JSONL, not terminal lines.
        compact={k:v for k,v in self.fields.items() if k not in {'last_resumable_checkpoint','selected_checkpoint'}
                 and not isinstance(v,(dict,list,tuple))}
        self.bar.set_postfix(compact, refresh=False)
        return row

    def advance(self, n=1, **fields):
        if n < 0 or self.completed+n > self.total:
            raise ValueError("completed progress outside explicit budget")
        self.completed += n
        self.bar.update(n)
        return self.record("completed_work", **fields)

    def start(self, **fields):
        """Show the in-flight method/family without claiming completed work."""
        row=self.record('STARTED_WORK',**fields)
        self.bar.refresh()
        return row

    def message(self, message):
        tqdm.write(message, file=sys.stderr)

    def close(self, status="STOPPED"):
        self.record(status)
        self.bar.close()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        self.close("INTERRUPTED" if kind is KeyboardInterrupt else "FAILED" if kind else "FINISHED")
