"""Research Notebook - Windows-native Streamlit Application.

Layout: Notebook | Sources | Ask | Brief
- Sources stored as individual JSON files under data/sources/
- Embedded Qdrant chunk ranking and context window packing (src/pack.py)
- Ask: Answers with verbatim quotes and explicit source_id
- Brief: Structured markdown {claim, evidence[], gaps, followups[]} saved to data/briefs/
- Web: Isolated DDGS search; appends 3 snippets labeled web: (never treated as uploaded sources)
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from sources_manager import pack_sources_for_context
from src.config import AGNES_BASE_URL, AGNES_MODEL, agnes_key_is_set
from src.ask import ask_question
from src.brief import generate_brief
from src.ingest import (
    PdfIngestSkipped,
    delete_source,
    get_source_point_counts,
    ingest_text,
    ingest_upload,
    load_sources,
)
from src.ocr_pages import list_ollama_tags
from src.pack import index_sources_to_qdrant

# Page configuration
st.set_page_config(
    page_title="Research Notebook",
    page_icon="📓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# Sidebar: Provider & Model Routing, Context Budget, Optional Web
# -----------------------------------------------------------------------------
st.sidebar.title("⚙️ Configuration")

selected_provider_id = "agnes"
selected_model = AGNES_MODEL
if not agnes_key_is_set():
    st.sidebar.error(
        "AGNESAI_API_KEY is unavailable. Set it as a Windows user environment variable."
    )
st.sidebar.caption(f"Model: `{AGNES_MODEL}`")
st.sidebar.caption(f"Base URL: `{AGNES_BASE_URL}`")

st.sidebar.divider()

# Agnes large-context budget slider (in characters)
st.sidebar.subheader("🎯 Context Window Cap")
char_budget = st.sidebar.slider(
    "Token budget (chars)",
    min_value=4_000,
    max_value=2_000_000,
    value=200_000,
    step=10_000,
    help="Character budget cap for ranking and packing source chunks into context.",
)
est_budget_tokens = char_budget // 4
st.sidebar.info(
    f"Budget Cap: **~{est_budget_tokens:,} tokens (estimate)** (`chars / 4`)"
)

retrieve_k = st.sidebar.slider(
    "Retrieve chunks (k)",
    min_value=1,
    max_value=50,
    value=12,
    help="Maximum number of ranked Qdrant chunks considered for context packing.",
)

st.sidebar.divider()

# Optional Web Search
st.sidebar.subheader("🌐 Web Augmentation")
enable_web_search = st.sidebar.checkbox(
    "Enable Web Search (DDGS)",
    value=False,
    help="Isolated DuckDuckGo search module. Appends 3 snippets labeled 'web:' (never treated as uploaded sources).",
)
force_ocr = st.sidebar.checkbox(
    "Force OCR",
    value=False,
    help="Route every PDF page through optional Ollama OCR after native extraction.",
)

st.sidebar.markdown("---")
st.sidebar.caption("Research Notebook • Native Windows 11")

# -----------------------------------------------------------------------------
# Load Data & Context Packing
# -----------------------------------------------------------------------------
sources = load_sources()
packing_result = pack_sources_for_context(sources, char_budget=char_budget)

# -----------------------------------------------------------------------------
# Main Navigation Tabs: Health | Sources | Notebook | Ask | Brief
# -----------------------------------------------------------------------------
tab_health, tab_sources, tab_notebook, tab_ask, tab_brief = st.tabs(
    ["Health", "Sources", "Notebook", "Ask", "Brief"]
)

# -----------------------------------------------------------------------------
# Tab 1: Health
# -----------------------------------------------------------------------------
with tab_health:
    st.header("Health")
    st.metric("AGNESAI_API_KEY", "Set" if agnes_key_is_set() else "Not set")
    st.caption("Only key presence is checked. The value is never displayed.")

    if st.button("Check Ollama tags"):
        try:
            ollama_tags = list_ollama_tags()
            if ollama_tags:
                st.code("\n".join(ollama_tags), language=None)
            else:
                st.info("Ollama is available but has no installed model tags.")
        except Exception as err:
            st.warning(f"Ollama tags unavailable: {err}")

# -----------------------------------------------------------------------------
# Tab 2: Notebook
# -----------------------------------------------------------------------------
with tab_notebook:
    st.header("Research Notebook Overview")

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Stored Sources", len(sources))
    with col2:
        st.metric(
            "Packed Sources", f"{len(packing_result.packed_sources)} / {len(sources)}"
        )
    with col3:
        st.metric(
            "Packed Characters",
            f"{packing_result.packed_chars:,} / {packing_result.budget_chars:,}",
        )
    with col4:
        st.metric(
            "Context Tokens (Estimate)",
            f"{packing_result.packed_tokens:,} / {packing_result.budget_tokens:,}",
        )

    st.progress(min(packing_result.utilization_pct / 100.0, 1.0))
    st.caption(f"Context budget utilization: **{packing_result.utilization_pct}%**")

    # Qdrant Vector Indexing Status
    col_idx1, col_idx2 = st.columns([3, 1])
    with col_idx1:
        st.subheader("Embedded Qdrant Vector Index (`data/qdrant`)")
        st.caption(
            "Chunks are indexed into local embedded Qdrant collection `sources` for ranking."
        )
    with col_idx2:
        if sources and st.button("🔄 Sync Vector Index"):
            with st.spinner("Indexing source chunks into embedded Qdrant..."):
                cnt = index_sources_to_qdrant(sources)
                st.success(f"Indexed {cnt} chunks into Qdrant.")

    st.subheader("Packed Context Inspection")
    if packing_result.packed_sources:
        with st.expander(
            f"View Packed Content ({packing_result.packed_chars:,} characters)",
            expanded=False,
        ):
            st.text_area(
                "Aggregated Prompt Context",
                value=packing_result.full_text,
                height=300,
                disabled=True,
            )

        st.write("**Included in context budget:**")
        for idx, src in enumerate(packing_result.packed_sources, start=1):
            st.markdown(
                f"- **#{idx}: {src.title}** (`{src.source_type}`) [ID: `{src.id[:8]}`] — {src.char_count:,} chars (~{src.est_tokens:,} tokens estimate)"
            )
    else:
        st.info("No sources packed yet. Add sources in the **Sources** tab.")

    if packing_result.excluded_sources:
        st.warning(
            f"{len(packing_result.excluded_sources)} source(s) excluded due to character budget limit:"
        )
        for src in packing_result.excluded_sources:
            st.markdown(
                f"- ⚠️ **{src.title}** ({src.char_count:,} chars / ~{src.est_tokens:,} tokens estimate)"
            )

# -----------------------------------------------------------------------------
# Tab 3: Sources
# -----------------------------------------------------------------------------
with tab_sources:
    st.header("Manage Research Sources")
    st.caption("Each source is stored as JSON in `data/sources/`.")
    for notice_type, notice in st.session_state.pop("source_notices", []):
        getattr(st, notice_type)(notice)

    # Source Ingestion Formats
    st.subheader("Add New Source")
    ingest_mode = st.radio(
        "Ingestion Method",
        ["Paste text", "Upload file (PDF / TXT / MD)"],
        horizontal=True,
    )

    if ingest_mode == "Paste text":
        with st.form("paste_source_form", clear_on_submit=True):
            paste_title = st.text_input(
                "Source Title", placeholder="e.g., Deep Learning Architecture Notes"
            )
            paste_content = st.text_area(
                "Content", height=180, placeholder="Paste your research text here..."
            )
            submit_paste = st.form_submit_button("Add Text Source")
            if submit_paste:
                if not paste_content.strip():
                    st.error("Please provide text content.")
                else:
                    try:
                        result = ingest_text(
                            paste_title or "Pasted Note", paste_content
                        )
                        st.success(
                            f"Added '{result.source.title}' with {result.point_count} chunks."
                        )
                        st.rerun()
                    except Exception as err:
                        st.error(str(err))

    elif ingest_mode == "Upload file (PDF / TXT / MD)":
        uploaded_file = st.file_uploader(
            "Choose a document",
            type=["pdf", "txt", "md"],
            help="Supported formats: PDF, TXT, Markdown",
        )
        if uploaded_file is not None:
            col_u1, col_u2 = st.columns([3, 1])
            with col_u1:
                custom_title = st.text_input(
                    "Custom Title (optional)", value=uploaded_file.name
                )
            with col_u2:
                st.write("")
                st.write("")
                process_btn = st.button("Process & Save File")

            if process_btn:
                try:
                    file_bytes = uploaded_file.read()
                    result = ingest_upload(
                        file_bytes,
                        uploaded_file.name,
                        custom_title,
                        force_ocr=force_ocr,
                    )
                    notices = [("warning", warning) for warning in result.warnings]
                    success = (
                        f"Uploaded '{result.source.title}' with "
                        f"{result.point_count} chunks."
                    )
                    if result.source.pdf_type:
                        success += (
                            f" PDF type: {result.source.pdf_type}; "
                            f"route: {result.source.route}."
                        )
                    notices.append(("success", success))
                    st.session_state["source_notices"] = notices
                    st.rerun()
                except PdfIngestSkipped as err:
                    st.warning(
                        f"PDF type: {err.pdf_type}; route: {err.route}. "
                        "No text was ingested."
                    )
                    for warning in err.warnings:
                        st.warning(warning)
                except Exception as err:
                    st.error(f"Error processing file: {err}")

    st.divider()

    # Sources List & Actions
    st.subheader(f"Current Sources ({len(sources)})")

    if not sources:
        st.info("No sources stored in `data/sources/` yet.")
    else:
        try:
            point_counts = get_source_point_counts([source.id for source in sources])
        except Exception as err:
            st.warning(str(err))
            point_counts = {}
        for idx, src in enumerate(sources):
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([4, 2, 2, 1])
                with c1:
                    st.markdown(f"**{src.title}**")
                    st.caption(f"ID: `{src.id}`")
                with c2:
                    st.markdown(f"Origin: `{src.origin}`")
                    st.caption(f"Chunks: {point_counts.get(src.id, 0)}")
                    if src.pdf_type:
                        st.caption(f"PDF type: `{src.pdf_type}`")
                        st.caption(f"Route: `{src.route}`")
                with c3:
                    st.markdown(f"**{src.char_count:,}** chars")
                    st.caption(f"~{src.est_tokens:,} tokens (estimate)")
                with c4:
                    if st.button("Delete", key=f"del_{src.id}"):
                        try:
                            delete_source(src.id)
                            st.rerun()
                        except Exception as err:
                            st.error(str(err))

                with st.expander("Preview Source Content"):
                    st.text(
                        src.content[:1500] + ("..." if len(src.content) > 1500 else "")
                    )

# -----------------------------------------------------------------------------
# Tab 4: Ask
# -----------------------------------------------------------------------------
with tab_ask:
    st.header("Ask Questions Across Research Sources")
    st.caption(
        "Answers grounded in ranked Qdrant chunks with verbatim quotes and explicit source_id citations."
    )

    st.info(
        f"Active Model: **{selected_model}** | "
        f"Context Cap: **{char_budget:,} chars (~{est_budget_tokens:,} tokens estimate)** | "
        f"Retrieve: **{retrieve_k} chunks** | "
        f"Web Search: **{'Enabled (Appends 3 web: snippets)' if enable_web_search else 'Disabled'}**"
    )

    user_query = st.text_input(
        "Enter your research question:",
        placeholder="e.g., What are the scaling limitations of standard multi-head attention?",
    )

    ask_button = st.button("Submit Question", type="primary")

    if ask_button:
        if not user_query.strip():
            st.warning("Please enter a question.")
        elif not sources:
            st.warning(
                "No sources available. Please add sources in the Sources tab first."
            )
        else:
            with st.spinner(
                f"Ranking chunks with embedded Qdrant and querying {selected_model}..."
            ):
                try:
                    result = ask_question(
                        query=user_query.strip(),
                        sources=sources,
                        char_cap=char_budget,
                        web_enabled=enable_web_search,
                        provider_id=selected_provider_id,
                        model_override=selected_model,
                        top_k=retrieve_k,
                    )

                    st.markdown("### Answer")
                    st.markdown(result["answer"])

                    if result.get("citations"):
                        st.markdown("### Grounded Citations List")
                        for idx, cite in enumerate(result["citations"], start=1):
                            st.markdown(
                                f'{idx}. `[{cite["source"]}]`: "{cite["quote"]}"'
                            )

                    st.divider()
                    st.caption(
                        f"Packed: **{result['packed_chars']:,} chars** (~{result['packed_tokens']:,} tokens estimate) "
                        f"across **{len(result['packed_chunks'])} Qdrant chunks**. Model: `{result['model_used']}`."
                    )

                    # Collapsible inspection of evidence chunks
                    with st.expander("View Cited Qdrant Chunks"):
                        for chk in result["packed_chunks"]:
                            st.markdown(
                                f"- **[{chk.source_id}] {chk.title}** (Score: `{chk.score:.3f}`): {chk.text[:200]}..."
                            )

                    if result.get("web_snippets"):
                        with st.expander(
                            "View Auxiliary Web Snippets (labeled web:)", expanded=False
                        ):
                            for s in result["web_snippets"]:
                                st.markdown(
                                    f"- **web: [{s['title']}]({s['href']})**\n  {s['text']}"
                                )
                    if result.get("web_error"):
                        st.warning(result["web_error"])

                except Exception as err:
                    st.error(f"Error executing query: {err}")

# -----------------------------------------------------------------------------
# Tab 5: Brief
# -----------------------------------------------------------------------------
with tab_brief:
    st.header("Research Synthesis Brief")
    st.caption(
        "Generate structured markdown briefs with {claim, evidence[], gaps, followups[]} saved to data/briefs/."
    )

    brief_topic = st.text_input(
        "Synthesis Topic / Research Question:",
        value="Scaling Limits of Attention and Dense Retrieval Strategies",
        placeholder="Enter research topic for the brief...",
    )

    generate_brief_btn = st.button("Generate Research Brief", type="primary")

    if generate_brief_btn:
        if not brief_topic.strip():
            st.warning("Please enter a topic.")
        elif not sources:
            st.warning(
                "No sources available. Please add sources in the Sources tab first."
            )
        else:
            with st.spinner(f"Synthesizing brief with {selected_model}..."):
                try:
                    brief_res = generate_brief(
                        topic=brief_topic.strip(),
                        sources=sources,
                        char_cap=char_budget,
                        web_enabled=enable_web_search,
                        provider_id=selected_provider_id,
                        model_override=selected_model,
                        top_k=retrieve_k,
                    )

                    st.success(
                        f"Brief generated and saved to `{brief_res['file_path']}`!"
                    )
                    st.markdown(brief_res["content"])
                    if brief_res.get("web_error"):
                        st.warning(brief_res["web_error"])

                    st.download_button(
                        label="📥 Download Brief (.md)",
                        data=brief_res["content"],
                        file_name=brief_res["filename"],
                        mime="text/markdown",
                    )
                except Exception as err:
                    st.error(f"Failed to generate brief: {err}")

    st.divider()
    st.subheader("Saved Briefs (`data/briefs/`)")
    briefs_dir = Path("data/briefs")
    if briefs_dir.exists():
        saved_brief_files = sorted(
            briefs_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        if saved_brief_files:
            for bf in saved_brief_files:
                with st.expander(f"📄 {bf.name} ({bf.stat().st_size:,} bytes)"):
                    st.code(bf.read_text(encoding="utf-8"), language="markdown")
        else:
            st.info("No saved briefs yet.")
    else:
        st.info("No saved briefs yet.")
