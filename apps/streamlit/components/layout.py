"""Shared page layout and controlled error rendering."""

import logging

import streamlit as st

LOGGER = logging.getLogger(__name__)


def title(name: str, description: str):
    st.title(name)
    st.caption(description)


def run_page(render):
    try:
        render()
    except Exception:
        LOGGER.exception("Dashboard page failed")
        st.error("Não foi possível carregar esta página. Verifique as fontes e o contrato de dados.")
