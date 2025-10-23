"""
Optional Gradio interface for the semantic code search engine.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import requests

from ..settings import settings

DEFAULT_API_ROOT = settings.frontend_api_root
DEFAULT_API_KEY = settings.frontend_api_key
API_KEY_HEADER = "X-API-Key"


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


def run() -> None:
    """Launch the Gradio UI."""
    try:
        import gradio as gr  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Gradio is not installed. Install it with `uv pip install gradio` to use this interface."
        ) from exc

    def _search(
        question: str,
        api_root: str,
        api_key: str,
        repo_filter: str,
        language_filter: str,
    ) -> tuple[str, List[List[str]], str]:
        if not question:
            return "Please enter a question.", [], ""

        key = api_key.strip() or None
        try:
            result = _run_query(api_root.strip() or DEFAULT_API_ROOT, key, question)
        except Exception as exc:
            return f"Query failed: {exc}", [], ""

        sources = result.get("sources", [])
        repo_filters = {r.strip() for r in repo_filter.split(",") if r.strip()}
        language_filters = {l.strip() for l in language_filter.split(",") if l.strip()}

        def _matches(source: Dict) -> bool:
            repo = source.get("repo")
            language = source.get("language")
            if repo_filters and repo not in repo_filters:
                return False
            if language_filters and language not in language_filters:
                return False
            return True

        filtered_sources = [src for src in sources if _matches(src)]
        rows = [
            [
                src.get("repo", ""),
                src.get("path", ""),
                src.get("language", ""),
                (src.get("snippet") or "")[:500],
            ]
            for src in filtered_sources
        ]
        meta = result.get("meta") or {}
        fallback_note = " (fallback answer)" if meta.get("fallback_used") else ""
        answer = result.get("answer", "No answer generated.") + fallback_note
        return answer, rows, repr(meta)

    def _load_filters(api_root: str, api_key: str) -> tuple[str, str]:
        try:
            repos = _fetch_repositories(api_root.strip() or DEFAULT_API_ROOT, api_key.strip() or None)
        except Exception:
            return "", ""
        repo_names = sorted({repo["name"] for repo in repos})
        languages = sorted({lang for repo in repos for lang in (repo.get("languages") or [])})
        return ", ".join(repo_names), ", ".join(languages)

    with gr.Blocks(title="Semantic Code Search") as demo:
        gr.Markdown("# Semantic Code Search Engine (Gradio)")
        with gr.Row():
            question = gr.Textbox(label="Question", placeholder="How is the HTTP client initialized?")
        with gr.Row():
            api_root = gr.Textbox(label="API root", value=DEFAULT_API_ROOT)
            api_key = gr.Textbox(label="API key", value=DEFAULT_API_KEY or "", type="password")
        with gr.Row():
            repo_filter = gr.Textbox(label="Filter repos (comma separated)")
            language_filter = gr.Textbox(label="Filter languages (comma separated)")
            load_filters_button = gr.Button("Load filters")
        answer = gr.Textbox(label="Answer", lines=6)
        meta = gr.Textbox(label="Metadata", lines=4)
        sources = gr.Dataframe(
            headers=["Repository", "Path", "Language", "Snippet"],
            datatype=["str", "str", "str", "str"],
            label="Sources",
        )
        search_button = gr.Button("Search", variant="primary")

        search_button.click(
            _search,
            inputs=[question, api_root, api_key, repo_filter, language_filter],
            outputs=[answer, sources, meta],
        )
        load_filters_button.click(
            _load_filters,
            inputs=[api_root, api_key],
            outputs=[repo_filter, language_filter],
        )

    demo.launch()


if __name__ == "__main__":  # pragma: no cover
    run()
