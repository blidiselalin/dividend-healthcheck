"""
In-place progress for synchronous sidebar operations (manage panel, imports).

Renders ``st.status`` + ``st.progress`` in the current container instead of the
global sidebar progress heading at the top.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

import streamlit as st

OperationProgressCallback = Callable[[str, float], None]


@contextmanager
def inline_operation_progress(
    title: str,
    *,
    expanded: bool = True,
) -> Iterator[OperationProgressCallback]:
    """Show step text and a progress bar in the active Streamlit frame."""
    with st.status(title, expanded=expanded) as status:
        progress_bar = st.progress(0.0, text="Starting…")
        failed = False

        def report(message: str, fraction: float) -> None:
            clamped = max(0.0, min(1.0, fraction))
            progress_bar.progress(clamped, text=message)
            status.update(label=f"{title} — {message}")

        try:
            yield report
        except Exception:
            failed = True
            status.update(label=f"{title} — failed", state="error")
            raise
        else:
            if not failed:
                status.update(label=title, state="complete")
