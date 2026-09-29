"""Repository construction; replace source adapters for future backends."""

import streamlit as st

from apps.streamlit.data.base import SparkSource
from apps.streamlit.data.gold_repository import GoldRepository
from apps.streamlit.data.observability_repository import ObservabilityRepository
from apps.streamlit.data.validation_repository import ValidationRepository


@st.cache_resource
def source():
    return SparkSource()


def gold():
    return GoldRepository(source())


def validation():
    return ValidationRepository(source())


def observability():
    return ObservabilityRepository(source())
