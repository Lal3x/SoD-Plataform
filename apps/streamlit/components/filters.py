"""Filter widgets backed by Gold values."""

import streamlit as st

from apps.streamlit.labels import field_label, label


def select_filters(repo, fields: list[str], prefix: str):
    filters = {}
    available = tuple(field for field in fields if field in repo.frame().columns)
    options_by_field = repo.get_filter_options(available)
    for field in available:
        options = options_by_field[field]
        display = ["Todos", *[label(option) for option in options]]
        chosen_display = st.selectbox(field_label(field), display, key=f"{prefix}_{field}")
        chosen = None if chosen_display == "Todos" else options[display.index(chosen_display) - 1]
        if chosen is not None:
            filters[field] = chosen
    return filters
