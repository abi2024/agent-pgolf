"""Streamlit dashboard for Parameter Golf experiment tracking.

Run with: streamlit run scripts/dashboard.py
"""

import json
import sqlite3
from pathlib import Path

try:
    import streamlit as st
except ImportError:
    print("Install streamlit: pip install streamlit")
    print("Then run: streamlit run scripts/dashboard.py")
    raise SystemExit(1)

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "pgolf.db"
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"


def get_db():
    if not DB_PATH.exists():
        st.warning("No database found. Run `python scripts/pgolf.py status` first to initialize.")
        return None
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


st.set_page_config(page_title="Parameter Golf Agent", page_icon="🏌️", layout="wide")
st.title("🏌️ Parameter Golf Agent Dashboard")

db = get_db()
if not db:
    st.stop()

# ─── Metrics Row ─────────────────────────────────────────────────────────────

col1, col2, col3, col4, col5 = st.columns(5)

best = db.execute("SELECT MIN(val_bpb) as v FROM experiments WHERE status='completed'").fetchone()["v"]
total = db.execute("SELECT COUNT(*) as n FROM experiments").fetchone()["n"]
completed = db.execute("SELECT COUNT(*) as n FROM experiments WHERE status='completed'").fetchone()["n"]
failed = db.execute("SELECT COUNT(*) as n FROM experiments WHERE status='failed'").fetchone()["n"]
cost = db.execute("SELECT COALESCE(SUM(cost_usd), 0) as c FROM experiments").fetchone()["c"]

col1.metric("Competition SOTA", "1.0810")
col2.metric("Your Best BPB", f"{best:.4f}" if best else "—", delta=f"{best - 1.0810:+.4f}" if best else None, delta_color="inverse")
col3.metric("Experiments", f"{completed}/{total}", f"{failed} failed")
col4.metric("Total Cost", f"${cost:.2f}")
col5.metric("Gap to SOTA", f"{best - 1.0810:+.4f}" if best else "—")

st.divider()

# ─── Tabs ────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs(["Experiments", "Techniques", "Knowledge Base", "Blog"])

# ── Tab 1: Experiments ──

with tab1:
    rows = db.execute(
        "SELECT * FROM experiments ORDER BY created_at DESC"
    ).fetchall()

    if rows:
        import pandas as pd
        df = pd.DataFrame([dict(r) for r in rows])
        display_cols = ["id", "status", "val_bpb", "artifact_size_bytes", "training_seconds", "hypothesis", "created_at"]
        available = [c for c in display_cols if c in df.columns]
        st.dataframe(
            df[available],
            use_container_width=True,
            column_config={
                "val_bpb": st.column_config.NumberColumn("BPB", format="%.4f"),
                "artifact_size_bytes": st.column_config.NumberColumn("Size (bytes)", format="%d"),
                "training_seconds": st.column_config.NumberColumn("Time (s)", format="%.0f"),
            },
        )

        # BPB progression chart
        completed_df = df[df["status"] == "completed"].sort_values("created_at")
        if len(completed_df) > 1 and "val_bpb" in completed_df.columns:
            st.subheader("BPB Progression")
            st.line_chart(completed_df.set_index("id")["val_bpb"])
    else:
        st.info("No experiments yet. Create one with `python scripts/pgolf.py track create`")

# ── Tab 2: Techniques ──

with tab2:
    tech_dir = KNOWLEDGE_DIR / "techniques"
    if tech_dir.exists():
        techniques = sorted(tech_dir.glob("*.md"))
        for t in techniques:
            with st.expander(t.stem.replace("_", " ").title()):
                st.markdown(t.read_text())
    else:
        st.info("No technique docs yet.")

# ── Tab 3: Knowledge Base ──

with tab3:
    kb_files = {
        "SOTA Timeline": KNOWLEDGE_DIR / "sota_timeline.md",
        "Lessons Learned": KNOWLEDGE_DIR / "lessons_learned.md",
        "Learning Path": KNOWLEDGE_DIR / "learning_path.md",
    }
    for name, path in kb_files.items():
        if path.exists():
            with st.expander(name):
                st.markdown(path.read_text())

# ── Tab 4: Blog ──

with tab4:
    drafts_dir = PROJECT_ROOT / "blog" / "drafts"
    published_dir = PROJECT_ROOT / "blog" / "published"

    st.subheader("Published")
    if published_dir.exists():
        published = sorted(published_dir.glob("*.md"))
        if published:
            for p in published:
                with st.expander(p.stem):
                    st.markdown(p.read_text())
        else:
            st.info("No published posts yet.")

    st.subheader("Drafts")
    if drafts_dir.exists():
        drafts = sorted(drafts_dir.glob("*.md"))
        if drafts:
            for d in drafts:
                with st.expander(d.stem):
                    st.markdown(d.read_text())
        else:
            st.info("No drafts yet. Generate one with `python scripts/pgolf.py blog --day 1`")

db.close()
