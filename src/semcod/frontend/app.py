"""
Streamlit interface for the semantic code search engine (Phase 5 enhancements).
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Dict, List, Optional

import requests
import streamlit as st

try:
    from ..settings import settings
except ImportError:  # When executed as a plain script via `streamlit run`
    import sys
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from semcod.settings import settings  # type: ignore  # noqa: E402

DEFAULT_API_ROOT = settings.frontend_api_root
DEFAULT_API_KEY = settings.frontend_api_key
API_KEY_HEADER = "X-API-Key"
HISTORY_LIMIT = 20


def _request(
    method: str,
    url: str,
    *,
    api_key: Optional[str] = None,
    timeout: int = 30,
    **kwargs,
):
    headers = kwargs.pop("headers", {})
    if api_key:
        headers[API_KEY_HEADER] = api_key
    response = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
    response.raise_for_status()
    return response


def _fetch_repositories(api_root: str, api_key: Optional[str]) -> List[Dict]:
    response = _request("GET", f"{api_root}/repos", api_key=api_key, timeout=15)
    return response.json()


def _run_query(api_root: str, api_key: Optional[str], question: str) -> Dict:
    payload = {"question": question}
    response = _request("POST", f"{api_root}/query", api_key=api_key, json=payload)
    return response.json()


def _ensure_session_defaults() -> None:
    st.session_state.setdefault("api_root", DEFAULT_API_ROOT)
    st.session_state.setdefault("api_key", DEFAULT_API_KEY or "")
    st.session_state.setdefault("query_history", [])
    st.session_state.setdefault("active_result", None)
    st.session_state.setdefault("last_question", "")


def _append_history(question: str, result: Dict) -> None:
    history: List[Dict] = st.session_state["query_history"]
    history.append({"question": question, "result": result})
    if len(history) > HISTORY_LIMIT:
        del history[0]


def _render_history() -> None:
    history: List[Dict] = st.session_state["query_history"]
    if not history:
        return
    with st.expander("Query history"):
        for idx, entry in enumerate(reversed(history)):
            label = entry["question"]
            if st.button(f"🔁 {label}", key=f"history-{idx}"):
                st.session_state["last_question"] = entry["question"]
                st.session_state["active_result"] = entry["result"]
                st.experimental_rerun()


def _filter_sources(
    sources: List[Dict],
    selected_repos: List[str],
    selected_languages: List[str],
) -> List[Dict]:
    repo_set = set(selected_repos)
    language_set = set(selected_languages)
    filtered: List[Dict] = []
    for source in sources:
        repo = source.get("repo") or "Unknown"
        language = source.get("language") or "Unknown"
        if repo_set and repo not in repo_set:
            continue
        if language_set and language not in language_set:
            continue
        filtered.append(source)
    return filtered


def _render_diff(sources: List[Dict]) -> None:
    if len(sources) < 2:
        return

    options = [
        f"{idx+1}. {src.get('repo', 'Unknown')} · {src.get('path', 'Unknown')}"
        for idx, src in enumerate(sources)
    ]
    left_idx = st.selectbox(
        "Left snippet",
        range(len(sources)),
        format_func=lambda i: options[i],
        key="diff-left",
    )
    right_idx = st.selectbox(
        "Right snippet",
        range(len(sources)),
        format_func=lambda i: options[i],
        key="diff-right",
    )

    if left_idx == right_idx:
        st.info("Select two different snippets to generate a diff.")
        return

    left = sources[left_idx]
    right = sources[right_idx]
    left_lines = (left.get("snippet") or "").splitlines()
    right_lines = (right.get("snippet") or "").splitlines()
    diff = "\n".join(
        difflib.unified_diff(
            left_lines,
            right_lines,
            fromfile=f"{left.get('repo', 'Unknown')}:{left.get('path', 'Unknown')}",
            tofile=f"{right.get('repo', 'Unknown')}:{right.get('path', 'Unknown')}",
            lineterm="",
        )
    )
    st.subheader("Diff view")
    st.code(diff or "No textual differences detected.", language="diff")


def run() -> None:
    """Entry point invoked by the CLI script."""
    _ensure_session_defaults()
    st.set_page_config(page_title="Semantic Code Search", layout="wide")
    st.title("Semantic Code Search Engine")

    api_root = st.session_state["api_root"]
    api_key = st.session_state["api_key"]

    with st.sidebar:
        st.header("Connection")
        api_root = st.text_input("API root", value=api_root or DEFAULT_API_ROOT)
        api_key = st.text_input("API key", value=api_key, type="password")
        st.session_state["api_root"] = api_root
        st.session_state["api_key"] = api_key

        st.divider()
        st.header("Repositories")
        repos: List[Dict] = []
        repo_names: List[str] = []
        languages: List[str] = []
        try:
            repos = _fetch_repositories(api_root, api_key or None)
            repo_names = sorted({repo["name"] for repo in repos})
            languages = sorted(
                {lang for repo in repos for lang in (repo.get("languages") or [])}
            )
        except Exception as exc:  # pragma: no cover - UI feedback only
            st.error(f"Failed to load repositories: {exc}")

        selected_repos = st.multiselect("Filter repos", repo_names, default=repo_names)
        language_options = languages or ["Unknown"]
        selected_languages = st.multiselect(
            "Filter languages", language_options, default=language_options
        )

        _render_history()

    question = st.text_input(
        "Ask a question about your codebase",
        value=st.session_state.get("last_question", ""),
    )
    col_search, col_reset = st.columns([1, 1])
    with col_search:
        trigger_search = st.button("Search", use_container_width=True)
    with col_reset:
        if st.button("Clear history", use_container_width=True):
            st.session_state["query_history"] = []
            st.session_state["active_result"] = None
            st.session_state["last_question"] = ""
            st.experimental_rerun()

    if trigger_search and question:
        with st.spinner("Running semantic search..."):
            try:
                result = _run_query(api_root, api_key or None, question)
            except Exception as exc:  # pragma: no cover - UI feedback only
                st.error(f"Query failed: {exc}")
                result = None
        if result:
            st.session_state["active_result"] = result
            st.session_state["last_question"] = question
            _append_history(question, result)

    result = st.session_state.get("active_result")
    if not result:
        return

    st.subheader("Answer")
    meta = result.get("meta") or {}
    answer_text = result.get("answer", "No answer generated.")
    fallback_used = meta.get("fallback_used", False)
    if fallback_used:
        st.warning(
            f"Fallback answer generated: {meta.get('reason', 'LLM unavailable')}"
        )
    st.write(answer_text)

    st.subheader("Sources")
    sources = result.get("sources", [])
    filtered_sources = _filter_sources(
        sources, selected_repos or [], selected_languages or []
    )
    if not filtered_sources:
        st.info("No sources match the current filters.")
    for source in filtered_sources:
        repo = source.get("repo", "unknown repo")
        path = source.get("path", "unknown file")
        language = source.get("language") or "unknown"
        st.markdown(f"**{repo}** · `{path}` · _{language}_")
        st.code(source.get("snippet", ""), language=language or "text")

    _render_diff(filtered_sources)


if __name__ == "__main__":  # pragma: no cover
    run()
