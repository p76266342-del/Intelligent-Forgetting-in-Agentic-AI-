"""Streamlit Interactive Dashboard for Intelligent Memory Management & Forgetting."""

import json
import sys
from datetime import datetime
from pathlib import Path

# Ensure 'backend/src' or 'src' is in sys.path for local discovery
root_dir = Path(__file__).parent.resolve()
for p in [str(root_dir / "backend" / "src"), str(root_dir / "src")]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pandas as pd
import streamlit as st

from intelligent_forgetting.agent import MemoryAgent
from intelligent_forgetting.config import get_settings
from intelligent_forgetting.forgetting_engine import ForgettingEngine
from intelligent_forgetting.memory_scorer import MemoryScorer
from intelligent_forgetting.memory_store import MemoryStore
from intelligent_forgetting.models import (
    AgentTaskRequest,
    ForgettingActionType,
    Memory,
    MemoryCategory,
    MemoryType,
    RetentionStatus,
)

# Page Configuration
st.set_page_config(
    page_title="Intelligent Forgetting in Agentic AI",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize Core Services
settings = get_settings()
store = MemoryStore(db_path=settings.database_path)
scorer = MemoryScorer(settings=settings)
engine = ForgettingEngine(memory_store=store, scorer=scorer, settings=settings)
agent = MemoryAgent(memory_store=store, forgetting_engine=engine, scorer=scorer, settings=settings)

# Header
st.title("🧠 Intelligent Forgetting in Agentic AI")
st.markdown(
    "Selective retention, cognitive pruning, and multi-factor memory lifecycle management "
    "for autonomous AI agents."
)

# Sidebar System Controls
st.sidebar.header("⚙️ Configuration & Thresholds")
st.sidebar.markdown(f"**Database:** `{settings.database_path}`")
st.sidebar.markdown(f"**Max Active Capacity:** `{settings.max_active_memories}` items")
st.sidebar.markdown(f"**Forget Threshold:** `{settings.forget_threshold}`")
st.sidebar.markdown(f"**Archive Threshold:** `{settings.archive_threshold}`")
st.sidebar.markdown(f"**Recency Half-Life:** `{settings.recency_half_life_hours}h`")

# Global Metrics
stats = store.get_stats()
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Memories", stats.total_memories)
col2.metric("Active", stats.active_count)
col3.metric("Archived", stats.archived_count)
col4.metric("Forgotten", stats.forgotten_count)
col5.metric("Active Context", f"~{stats.estimated_active_tokens} tokens")

tabs = st.tabs(["📊 Memory Explorer", "🧪 Forgetting Engine (Dry-Run)", "🤖 Agent Simulator", "➕ Add Memory"])

# ----------------- TAB 1: MEMORY EXPLORER -----------------
with tabs[0]:
    st.subheader("Persistent Memory Store")
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    status_filter = filter_col1.selectbox(
        "Filter by Status",
        options=["ALL (Exclude Forgotten)", "active", "archived", "forgotten", "summarized", "ALL (Including Forgotten)"],
        index=0,
    )
    cat_filter = filter_col2.selectbox(
        "Filter by Category",
        options=["ALL", "fact", "preference", "conversation", "task_context", "system", "general"],
        index=0,
    )
    search_q = filter_col3.text_input("Quick Search", placeholder="e.g. database, python...")

    # Load memories
    if status_filter == "ALL (Exclude Forgotten)":
        memories = store.list_memories(include_forgotten=False, limit=500)
    elif status_filter == "ALL (Including Forgotten)":
        memories = store.list_memories(include_forgotten=True, limit=500)
    else:
        memories = store.list_memories(status=RetentionStatus(status_filter), limit=500)

    if cat_filter != "ALL":
        memories = [m for m in memories if m.category.value == cat_filter]

    if search_q.strip():
        memories = [m for m in memories if search_q.lower() in m.content.lower()]

    if not memories:
        st.info("No memories match the selected criteria.")
    else:
        df_rows = []
        for m in memories:
            df_rows.append({
                "ID": m.id[:8] + "...",
                "Content": m.content,
                "Importance": m.importance,
                "Access Count": m.access_count,
                "Status": m.retention_status.value,
                "Category": m.category.value,
                "Type": m.memory_type.value,
                "Pinned": "📌 Yes" if m.is_pinned else "No",
                "Critical": "🛡️ Yes" if m.is_critical else "No",
                "Last Accessed": m.last_accessed_at.strftime("%Y-%m-%d %H:%M"),
                "Score": f"{m.retention_score:.3f}" if m.retention_score is not None else "N/A",
            })
        st.dataframe(pd.DataFrame(df_rows), use_container_width=True)

        st.markdown("#### Manage Specific Memory")
        selected_id = st.selectbox(
            "Select Memory to inspect or modify",
            options=[m.id for m in memories],
            format_func=lambda x: f"{x[:8]} - {next(m.content[:60] for m in memories if m.id == x)}...",
        )
        if selected_id:
            target_mem = next(m for m in memories if m.id == selected_id)
            c1, c2, c3, c4 = st.columns(4)
            if target_mem.is_pinned:
                if c1.button("Unpin Memory", key=f"unpin_{target_mem.id}"):
                    store.set_pinned(target_mem.id, False)
                    st.rerun()
            else:
                if c1.button("📌 Pin Memory", key=f"pin_{target_mem.id}"):
                    store.set_pinned(target_mem.id, True)
                    st.rerun()

            if target_mem.is_critical:
                if c2.button("Clear Critical Flag", key=f"uncrit_{target_mem.id}"):
                    store.set_critical(target_mem.id, False)
                    st.rerun()
            else:
                if c2.button("🛡️ Mark Critical", key=f"crit_{target_mem.id}"):
                    store.set_critical(target_mem.id, True)
                    st.rerun()

            new_imp = c3.slider("Adjust Importance", 0.0, 1.0, float(target_mem.importance), 0.05, key="slider_imp")
            if c3.button("Update Importance"):
                store.update_importance(target_mem.id, new_imp)
                st.rerun()

            if c4.button("Archive Memory", key=f"arch_{target_mem.id}"):
                store.archive_memory(target_mem.id)
                st.rerun()

# ----------------- TAB 2: FORGETTING ENGINE (DRY-RUN) -----------------
with tabs[1]:
    st.subheader("Intelligent Forgetting Evaluation & Simulation")
    st.markdown(
        "Evaluate active memories against retention thresholds, redundancy clusters, and capacity constraints. "
        "Review proposed actions in **Dry-Run Mode** before applying persistent changes."
    )

    task_ctx = st.text_input(
        "Current Task Context (optional, informs task relevance scoring)",
        placeholder="e.g. Building an automated Python deployment script",
    )

    eval_btn = st.button("🔍 Run Dry-Run Evaluation", type="primary")

    if eval_btn or "last_eval" in st.session_state:
        if eval_btn:
            with st.spinner("Calculating multi-dimensional retention scores..."):
                eval_res = engine.evaluate(task_context=task_ctx if task_ctx else None, dry_run=True)
                st.session_state["last_eval"] = eval_res
        else:
            eval_res = st.session_state["last_eval"]

        st.success(f"Evaluation completed at {eval_res.evaluated_at.strftime('%H:%M:%S UTC')} (Dry-Run Mode)")

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Active (Before)", eval_res.total_active_before)
        m2.metric("Retain Proposed", eval_res.retained_count)
        m3.metric("Summarize Proposed", eval_res.summarized_count)
        m4.metric("Archive Proposed", eval_res.archived_count)
        m5.metric("Forget Proposed", eval_res.forgotten_count)

        st.info(f"💡 Estimated token savings from proposed actions: **{eval_res.estimated_token_savings} tokens**")

        st.markdown("### Proposed Actions Matrix")
        action_rows = []
        for a in eval_res.actions_proposed:
            mem = store.get_memory(a.memory_id)
            action_rows.append({
                "Memory ID": a.memory_id[:8] + "...",
                "Content": mem.content if mem else "N/A",
                "Action": a.action.value.upper(),
                "Retention Score": f"{a.score:.4f}",
                "Protected": "🛡️ Yes" if (mem and mem.is_protected()) else "No",
                "Reason / Decision Logic": a.reason,
            })
        st.dataframe(pd.DataFrame(action_rows), use_container_width=True)

        st.markdown("---")
        st.warning("⚠️ Applying these actions will update the persistent SQLite database.")
        if st.button("🚀 Apply Forgetting Actions Now", type="secondary"):
            with st.spinner("Applying evaluated actions to persistent memory store..."):
                applied_counts = engine.apply(eval_res, task_context=task_ctx)
                st.session_state.pop("last_eval", None)
                st.success(
                    f"Successfully applied forgetting actions: "
                    f"{applied_counts.get('retained', 0)} retained, "
                    f"{applied_counts.get('summarized', 0)} summarized, "
                    f"{applied_counts.get('archived', 0)} archived, "
                    f"{applied_counts.get('forgotten', 0)} forgotten."
                )
                st.rerun()

# ----------------- TAB 3: AGENT SIMULATOR -----------------
with tabs[2]:
    st.subheader("Agent Task Simulation & Context Synthesis")
    st.markdown("Send a prompt or task to the demonstration agent to observe retrieval, context synthesis, and memory formation.")

    agent_input = st.text_area(
        "User Task / Instruction",
        value="I always prefer PostgreSQL over MySQL for production databases. What database should we choose for our new service?",
        height=100,
    )
    col_opt1, col_opt2 = st.columns(2)
    record_conv = col_opt1.checkbox("Record interaction memories", value=True)
    trigger_forgetting = col_opt2.checkbox("Trigger forgetting evaluation", value=False)

    if st.button("Run Agent Interaction"):
        with st.spinner("Processing agent lifecycle..."):
            req = AgentTaskRequest(
                task=agent_input,
                record_conversation=record_conv,
                run_forgetting_eval=trigger_forgetting,
            )
            resp = agent.process_task(req)

            st.markdown("#### 1. Retrieved Retained Memories")
            if resp.retrieved_memories:
                for r in resp.retrieved_memories:
                    st.markdown(f"- **[{r.category.value}]** (Score: {r.retention_score:.3f}): {r.content}")
            else:
                st.write("No matching memories in active storage.")

            st.markdown("#### 2. Synthesized Agent Output")
            st.code(resp.response_text, language="markdown")

            st.markdown("#### 3. New Memories Formed")
            if resp.new_memories_created:
                for c in resp.new_memories_created:
                    st.write(f"- Created `[{c.category.value}]`: {c.content} (Importance: {c.importance})")
            else:
                st.write("No new memories were recorded.")

# ----------------- TAB 4: ADD MEMORY -----------------
with tabs[3]:
    st.subheader("Manually Ingest Memory")
    with st.form("manual_memory_form"):
        content_in = st.text_area("Memory Content", placeholder="Enter memory text...")
        c1, c2, c3 = st.columns(3)
        imp_in = c1.slider("Importance", 0.0, 1.0, 0.5, 0.05)
        cat_in = c2.selectbox("Category", [c.value for c in MemoryCategory])
        type_in = c3.selectbox("Type", [t.value for t in MemoryType])

        c4, c5 = st.columns(2)
        pinned_in = c4.checkbox("📌 Pin memory (prevent all deletion/archiving)")
        critical_in = c5.checkbox("🛡️ Mark Critical")

        tags_in = st.text_input("Tags (comma separated)", placeholder="backend, postgres, config")

        submitted = st.form_submit_button("Save Memory to Store")
        if submitted:
            if not content_in.strip():
                st.error("Content cannot be empty.")
            else:
                tag_list = [t.strip() for t in tags_in.split(",") if t.strip()]
                mem = Memory(
                    content=content_in.strip(),
                    importance=imp_in,
                    category=MemoryCategory(cat_in),
                    memory_type=MemoryType(type_in),
                    is_pinned=pinned_in,
                    is_critical=critical_in,
                    tags=tag_list,
                )
                score, breakdown = scorer.score_memory(mem)
                mem.retention_score = score
                mem.score_breakdown = breakdown
                saved = store.save_memory(mem)
                st.success(f"Memory saved successfully! ID: `{saved.id}` (Initial Score: {score:.3f})")
                st.rerun()
