"""Trading scheduler package.

Periodically runs catchup and daily data verification jobs inside Docker.
Entry point: `python -m trading.scheduler.main`. Khong re-export main o day:
import main tu __init__ lam `python -m` in RuntimeWarning (runpy).
"""
