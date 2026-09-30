"""Snapshot-aware cache for read-only dashboard queries."""

from __future__ import annotations

from functools import wraps

import streamlit as st


def cached_gold_query(*, ttl: int = 600, max_entries: int = 128):
    """Cache a repository method by Gold snapshot, arguments and bounded TTL."""

    def decorate(function):
        @st.cache_data(ttl=ttl, max_entries=max_entries, show_spinner=False)
        def query(
            _repository, method_name: str, snapshot: str, args: tuple, kwargs: dict
        ):
            return function(_repository, *args, **kwargs)

        @wraps(function)
        def wrapped(self, *args, **kwargs):
            return query(
                self, function.__qualname__, self.snapshot_token(), args, kwargs
            )

        return wrapped

    return decorate
