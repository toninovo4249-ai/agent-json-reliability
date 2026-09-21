from __future__ import annotations

import time


class Clock:
    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *args):
        return False

    @property
    def ms(self) -> float:
        return (time.perf_counter() - self.t0) * 1000.0
