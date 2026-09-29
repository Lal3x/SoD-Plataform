"""Metric presentation helpers."""

import streamlit as st


def count(label: str, value, help_text: str | None = None):
    st.metric(label, "não disponível" if value is None else f"{value:,}".replace(",", "."), help=help_text)


def percent(label: str, value, help_text: str | None = None):
    st.metric(label, "não disponível" if value is None else f"{value:.2%}".replace(".", ","), help=help_text)
