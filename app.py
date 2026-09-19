"""Research Notebook - Windows-native Streamlit Application.

Layout: Notebook | Sources | Ask | Brief
- Sources stored as JSONL under data/sources/sources.jsonl
- Embedded Qdrant chunk ranking and context window packing (src/pack.py)
- Ask: Answers with verbatim quotes and explicit source_id
- Brief: Structured markdown {claim, evidence[], gaps, followups[]} saved to data/briefs/
- Web: Isolated DDGS search; appends 3 snippets labeled web: (never treated as uploaded sources)
"""

from __future__ import annotations

from pathlib import Path
import streamlit as st

from client import get_available_providers
from sources_manager import (
    load_sources,
    add_source,
    delete_source,
    clear_sources,
    extract_text_from_pdf,
    extract_text_from_txt,
    fetch_url_text,
    pack_sources_for_context,
)
from src.pack import index_sources_to_qdrant, rank_and_pack_chunks
from synthesis import ask_question, generate_brief
from web_search import search_web

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

# Provider Routing
available_providers = get_available_providers()
provider_keys = list(available_providers.keys())

if not provider_keys:
    st.sidebar.error("⚠️ No configured provider found! Set AGNESAI_API_KEY.")
    selected_provider_id = "agnes"
    selected_model = "agnes-3.0-flash"
else:
    default_index = provider_keys.index("agnes") if "agnes" in provider_keys else 0
    selected_provider_id = st.sidebar.selectbox(
        "LLM Provider",
        options=provider_keys,
        index=default_index,
        format_func=lambda pid: available_providers[pid].display_name,
    )
    provider_info = available_providers[selected_provider_id]
    selected_model = st.sidebar.selectbox(
        "Model",
        options=provider_info.models,
        index=0,
    )
    st.sidebar.caption(f"Base URL: `{provider_info.base_url}`")

st.sidebar.divider()

# Agnes 512K Context Budget Slider (in characters)
st.sidebar.subheader("🎯 Context Window Cap")
char_budget = st.sidebar.slider(
    "Character Budget Cap",
    min_value=4_000,
    max_value=2_000_000,
    value=200_000,
    step=10_000,
    help="Character budget cap for ranking and packing source chunks into context.",
)
est_budget_tokens = char_budget // 4
st.sidebar.info(f"Budget Cap: **~{est_budget_tokens:,} tokens (estimate)** (`chars / 4`)")

st.sidebar.divider()

# Optional Web Search
st.sidebar.subheader("🌐 Web Augmentation")
enable_web_search = st.sidebar.checkbox(
    "Enable Web Search (DDGS)",
    value=False,
    help="Isolated DuckDuckGo search module. Appends 3 snippets labeled 'web:' (never treated as uploaded sources).",
)

st.sidebar.markdown("---")
st.sidebar.caption("Research Notebook • Native Windows 11")

# -----------------------------------------------------------------------------
# Load Data & Context Packing
# -----------------------------------------------------------------------------
sources = load_sources()
packing_result = pack_sources_for_context(sources, char_budget=char_budget)

# -----------------------------------------------------------------------------
# Main Navigation Tabs: Notebook | Sources | Ask | Brief
# -----------------------------------------------------------------------------
tab_notebook, tab_sources, tab_ask, tab_brief = st.tabs(
    ["📓 Notebook", "📚 Sources", "💬 Ask", "📝 Brief"]
)

# -----------------------------------------------------------------------------
# Tab 1: Notebook
# -----------------------------------------------------------------------------
with tab_notebook:
    st.header("Research Notebook Overview")

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Stored Sources", len(sources))
    with col2:
        st.metric("Packed Sources", f"{len(packing_result.packed_sources)} / {len(sources)}")
    with col3:
        st.metric("Packed Characters", f"{packing_result.packed_chars:,} / {packing_result.budget_chars:,}")
    with col4:
        st.metric("Context Tokens (Estimate)", f"{packing_result.packed_tokens:,} / {packing_result.budget_tokens:,}")

    st.progress(min(packing_result.utilization_pct / 100.0, 1.0))
    st.caption(f"Context budget utilization: **{packing_result.utilization_pct}%**")

    # Qdrant Vector Indexing Status
    col_idx1, col_idx2 = st.columns([3, 1])
    with col_idx1:
        st.subheader("Embedded Qdrant Vector Index (`data/qdrant`)")
        st.caption("Chunks are indexed into local embedded Qdrant for semantic ranking.")
    with col_idx2:
        if sources and st.button("🔄 Sync Vector Index"):
            with st.spinner("Indexing source chunks into embedded Qdrant..."):
                cnt = index_sources_to_qdrant(sources)
                st.success(f"Indexed {cnt} chunks into Qdrant.")

    st.subheader("Packed Context Inspection")
    if packing_result.packed_sources:
        with st.expander(f"View Packed Content ({packing_result.packed_chars:,} characters)", expanded=False):
            st.text_area(
                "Aggregated Prompt Context",
                value=packing_result.full_text,
                height=300,
                disabled=True,
            )
        
        st.write("**Included in context budget:**")
        for idx, src in enumerate(packing_result.packed_sources, start=1):
            st.markdown(f"- **#{idx}: {src.title}** (`{src.source_type}`) [ID: `{src.id[:8]}`] — {src.char_count:,} chars (~{src.est_tokens:,} tokens estimate)")
    else:
        st.info("No sources packed yet. Add sources in the **Sources** tab.")

    if packing_result.excluded_sources:
        st.warning(f"{len(packing_result.excluded_sources)} source(s) excluded due to character budget limit:")
        for src in packing_result.excluded_sources:
            st.markdown(f"- ⚠️ **{src.title}** ({src.char_count:,} chars / ~{src.est_tokens:,} tokens estimate)")

# -----------------------------------------------------------------------------
# Tab 2: Sources
# -----------------------------------------------------------------------------
with tab_sources:
    st.header("Manage Research Sources")
    st.caption("All sources are stored as JSONL in `data/sources/sources.jsonl`.")

    # Source Ingestion Formats
    st.subheader("Add New Source")
    ingest_mode = st.radio(
        "Ingestion Method",
        ["Paste Text", "Upload File (PDF / TXT / MD)", "Fetch Web URL"],
        horizontal=True,
    )

    if ingest_mode == "Paste Text":
        with st.form("paste_source_form", clear_on_submit=True):
            paste_title = st.text_input("Source Title", placeholder="e.g., Deep Learning Architecture Notes")
            paste_content = st.text_area("Content", height=180, placeholder="Paste your research text here...")
            submit_paste = st.form_submit_button("Add Text Source")
            if submit_paste:
                if not paste_content.strip():
                    st.error("Please provide text content.")
                else:
                    item = add_source(
                        title=paste_title or "Pasted Note",
                        content=paste_content,
                        source_type="paste",
                    )
                    # Automatically index new source to Qdrant
                    index_sources_to_qdrant([item])
                    st.success(f"Added source '{item.title}' ({item.char_count:,} chars, ~{item.est_tokens:,} tokens estimate).")
                    st.rerun()

    elif ingest_mode == "Upload File (PDF / TXT / MD)":
        uploaded_file = st.file_uploader(
            "Choose a document",
            type=["pdf", "txt", "md"],
            help="Supported formats: PDF, TXT, Markdown",
        )
        if uploaded_file is not None:
            col_u1, col_u2 = st.columns([3, 1])
            with col_u1:
                custom_title = st.text_input("Custom Title (optional)", value=uploaded_file.name)
            with col_u2:
                st.write("")
                st.write("")
                process_btn = st.button("Process & Save File")

            if process_btn:
                try:
                    file_bytes = uploaded_file.read()
                    if uploaded_file.name.lower().endswith(".pdf"):
                        extracted_text = extract_text_from_pdf(file_bytes)
                    else:
                        extracted_text = extract_text_from_txt(file_bytes)

                    if not extracted_text.strip():
                        st.warning("No extractable text found in file.")
                    else:
                        item = add_source(
                            title=custom_title or uploaded_file.name,
                            content=extracted_text,
                            source_type="upload",
                            filename=uploaded_file.name,
                        )
                        index_sources_to_qdrant([item])
                        st.success(f"Uploaded and indexed '{item.title}' ({item.char_count:,} chars, ~{item.est_tokens:,} tokens estimate).")
                        st.rerun()
                except Exception as err:
                    st.error(f"Error processing file: {err}")

    elif ingest_mode == "Fetch Web URL":
        with st.form("url_source_form"):
            url_input = st.text_input("Web URL", placeholder="https://example.com/article")
            custom_url_title = st.text_input("Custom Title (optional)", placeholder="Leave blank to use page title")
            submit_url = st.form_submit_button("Fetch & Ingest URL")
            if submit_url:
                if not url_input.strip():
                    st.error("Please enter a valid URL.")
                else:
                    with st.spinner("Fetching URL content..."):
                        try:
                            page_title, page_content = fetch_url_text(url_input.strip())
                            if not page_content.strip():
                                st.warning("Fetched page has empty content.")
                            else:
                                final_title = custom_url_title.strip() or page_title or url_input
                                item = add_source(
                                    title=final_title,
                                    content=page_content,
                                    source_type="url",
                                    url=url_input.strip(),
                                )
                                index_sources_to_qdrant([item])
                                st.success(f"Ingested and indexed '{item.title}' ({item.char_count:,} chars, ~{item.est_tokens:,} tokens estimate).")
                                st.rerun()
                        except Exception as err:
                            st.error(f"Failed to fetch URL: {err}")

    st.divider()

    # Sources List & Actions
    col_hdr, col_actions = st.columns([3, 1])
    with col_hdr:
        st.subheader(f"Current Sources ({len(sources)})")
    with col_actions:
        if sources and st.button("🗑️ Clear All Sources"):
            clear_sources()
            st.rerun()

    if not sources:
        st.info("No sources stored in `data/sources/sources.jsonl` yet.")
    else:
        for idx, src in enumerate(sources):
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([4, 2, 2, 1])
                with c1:
                    st.markdown(f"**{src.title}**")
                    st.caption(f"ID: `{src.id}`")
                    if src.filename:
                        st.caption(f"📁 {src.filename}")
                    elif src.url:
                        st.caption(f"🔗 {src.url}")
                with c2:
                    st.markdown(f"Type: `{src.source_type}`")
                    st.caption(f"Added: {src.created_at[:19]}")
                with c3:
                    st.markdown(f"**{src.char_count:,}** chars")
                    st.caption(f"~{src.est_tokens:,} tokens (estimate)")
                with c4:
                    if st.button("Delete", key=f"del_{src.id}"):
                        delete_source(src.id)
                        st.rerun()

                with st.expander("Preview Source Content"):
                    st.text(src.content[:1500] + ("..." if len(src.content) > 1500 else ""))

# -----------------------------------------------------------------------------
# Tab 3: Ask
# -----------------------------------------------------------------------------
with tab_ask:
    st.header("Ask Questions Across Research Sources")
    st.caption("Answers grounded in ranked Qdrant chunks with verbatim quotes and explicit source_id citations.")

    st.info(
        f"Active Model: **{selected_model}** | "
        f"Context Cap: **{char_budget:,} chars (~{est_budget_tokens:,} tokens estimate)** | "
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
            st.warning("No sources available. Please add sources in the Sources tab first.")
        else:
            with st.spinner(f"Ranking chunks with embedded Qdrant and querying {selected_model}..."):
                try:
                    result = ask_question(
                        query=user_query.strip(),
                        sources=sources,
                        char_cap=char_budget,
                        web_enabled=enable_web_search,
                        provider_id=selected_provider_id,
                        model_override=selected_model,
                    )

                    st.markdown("### Answer")
                    st.markdown(result["answer"])

                    if result.get("citations"):
                        st.markdown("### Grounded Citations List")
                        for idx, cite in enumerate(result["citations"], start=1):
                            st.markdown(f"{idx}. `[{cite['source']}]`: \"{cite['quote']}\"")

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
                        with st.expander("View Auxiliary Web Snippets (labeled web:)", expanded=False):
                            for s in result["web_snippets"]:
                                st.markdown(f"- **web: [{s['title']}]({s['href']})**\n  {s['body']}")

                except Exception as err:
                    st.error(f"Error executing query: {err}")

# -----------------------------------------------------------------------------
# Tab 4: Brief
# -----------------------------------------------------------------------------
with tab_brief:
    st.header("Research Synthesis Brief")
    st.caption("Generate structured markdown briefs with {claim, evidence[], gaps, followups[]} saved to data/briefs/.")

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
            st.warning("No sources available. Please add sources in the Sources tab first.")
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
                    )

                    st.success(f"Brief generated and saved to `{brief_res['file_path']}`!")
                    st.markdown(brief_res["content"])

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
        saved_brief_files = sorted(briefs_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if saved_brief_files:
            for bf in saved_brief_files:
                with st.expander(f"📄 {bf.name} ({bf.stat().st_size:,} bytes)"):
                    st.code(bf.read_text(encoding="utf-8"), language="markdown")
        else:
            st.info("No saved briefs yet.")
    else:
        st.info("No saved briefs yet.")
