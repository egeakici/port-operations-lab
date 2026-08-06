from __future__ import annotations


APP_CSS = """
<style>
.cc-subtitle {
    color: #b9cbd2;
    font-size: 1.02rem;
    margin-top: -0.5rem;
}
.cc-strip {
    border: 1px solid rgba(244, 248, 250, 0.14);
    border-radius: 6px;
    padding: 0.65rem 0.75rem;
    background: rgba(16, 42, 54, 0.52);
}
.cc-status {
    font-weight: 650;
    letter-spacing: 0;
}
.cc-ok { color: #2ec4b6; }
.cc-error { color: #ffbf69; }
.cc-layout {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
}
.cc-layout th,
.cc-layout td {
    border: 1px solid rgba(244, 248, 250, 0.16);
    padding: 0.45rem;
    overflow-wrap: anywhere;
}
.cc-chip {
    display: inline-block;
    padding: 0.1rem 0.42rem;
    border-radius: 999px;
    border: 1px solid rgba(46, 196, 182, 0.35);
    color: #f4f8fa;
    background: rgba(46, 196, 182, 0.08);
}
</style>
"""


def apply_styles() -> None:
    import streamlit as st

    st.markdown(APP_CSS, unsafe_allow_html=True)

