"""
Streamlit interface for the semantic code search engine.
"""
from __future__ import annotations

import streamlit as st
import requests

API_ROOT = "http://localhost:8000"


def _fetch_repositories() -> list[dict]:
    response = requests.get(f"{API_ROOT}/repos", timeout=10)
    response.raise_for_status()
    return response.json()


def _run_query(question: str) -> dict:
    response = requests.post(f"{API_ROOT}/query", json={"question": question}, timeout=30)
    response.raise_for_status()
    return response.json()


def run() -> None:
    """Entry point invoked by the CLI script."""
    st.set_page_config(page_title="Semantic Code Search", layout="wide")
    st.title("Semantic Code Search Engine")

    with st.sidebar:
        st.header("Repositories")
        try:
            repos = _fetch_repositories()
            for repo in repos:
                st.markdown(f"- **{repo['name']}** – {repo.get('revision') or 'latest'}")
        except Exception as exc:  # pragma: no cover - UI feedback only
            st.error(f"Failed to load repositories: {exc}")

    question = st.text_input("Ask a question about your codebase")
    if st.button("Search") and question:
        with st.spinner("Running semantic search..."):
            try:
                result = _run_query(question)
                st.subheader("Answer")
                st.write(result.get("answer", "No answer generated."))
                st.subheader("Sources")
                for source in result.get("sources", []):
                    repo = source.get("repo", "unknown repo")
                    path = source.get("path", "unknown file")
                    snippet = source.get("snippet", "")
                    st.markdown(f"**{repo}** · `{path}`")
                    st.code(snippet, language=source.get("language") or "text")
            except Exception as exc:  # pragma: no cover - UI feedback only
                st.error(f"Query failed: {exc}")


if __name__ == "__main__":  # pragma: no cover
    run()
