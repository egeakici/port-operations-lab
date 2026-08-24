from __future__ import annotations


APP_CSS = """
<style>
.mps-subtitle {
    color: #b9cbd2;
    font-size: 1.02rem;
    margin-top: -0.5rem;
}
.mps-strip {
    border: 1px solid rgba(244, 248, 250, 0.14);
    border-radius: 6px;
    padding: 0.7rem 0.8rem;
    background: rgba(16, 42, 54, 0.50);
}
.mps-card {
    border: 1px solid rgba(244, 248, 250, 0.14);
    border-radius: 6px;
    padding: 0.7rem 0.8rem;
    background: rgba(15, 28, 38, 0.52);
    min-height: 92px;
}
.mps-card-label {
    color: #9fb4c2;
    font-size: 0.82rem;
}
.mps-card-value {
    color: #f4f8fa;
    font-size: 1.45rem;
    font-weight: 720;
    letter-spacing: 0;
}
.mps-chip {
    display: inline-block;
    padding: 0.12rem 0.45rem;
    border-radius: 999px;
    border: 1px solid rgba(46, 196, 182, 0.35);
    color: #f4f8fa;
    background: rgba(46, 196, 182, 0.08);
    margin-right: 0.25rem;
}
.mps-muted {
    color: #9fb4c2;
}
</style>
"""


def apply_styles() -> None:
    import streamlit as st

    st.markdown(APP_CSS, unsafe_allow_html=True)

