"""
Engineering College Dashboard — Live File Watcher (No API)
===========================================================
pip install streamlit pandas plotly openpyxl watchdog

Run:
    streamlit run college_dashboard.py

HOW DYNAMIC UPDATES WORK:
  - Set LOCAL_FILE to your Excel file path below
  - Dashboard polls every POLL_SECONDS for file changes (MD5 hash check)
  - When you save/edit your Excel, the dashboard auto-refreshes within POLL_SECONDS
  - OR just re-upload the file in the sidebar anytime

Set LOCAL_FILE = None to use upload-only mode.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO
import hashlib, os, time
from datetime import datetime

# ══════════════════════════════════════════════════════════════════════════════
#  ★  SET THIS TO YOUR EXCEL FILE PATH FOR AUTO LIVE UPDATES  ★
# ══════════════════════════════════════════════════════════════════════════════
#LOCAL_FILE   = r"C:\Users\adity\Downloads\Engineering_College_Management.xlsx"  # e.g. r"C:\Users\You\Desktop\Engineering_College_Management.xlsx"
LOCAL_FILE=None
POLL_SECONDS = 3      # how often to check for file changes (seconds)
# ══════════════════════════════════════════════════════════════════════════════

KEEP_COLS = {
    "Faculty_Details":    ["College","Branch","Faculty ID","Name","Designation"],
    "Student_Details":    ["College","Branch","Roll No","Name","Year","Div"],
    "Faculty_Attendance": ["College","Branch","Name","Total %"],
    "Student_Attendance": ["College","Branch","Name","Year","Total %"],
    "Student_Marks":      ["College","Branch","Roll No","Name","Year",
                           "ISE 1","Mid Term","End Term","Grand\nTotal"],
}

# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="College Dashboard", page_icon="🎓",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');
:root{--navy:#0f1b2d;--teal:#00b4d8;--mint:#06d6a0;--amber:#ffb703;
      --coral:#ef476f;--card:#162032;--border:#1e3a5f;--text:#e8f0fe;--muted:#7a9abf;}
html,body,[data-testid="stAppViewContainer"]{background:var(--navy)!important;color:var(--text)!important;font-family:'DM Sans',sans-serif;}
[data-testid="stSidebar"]{background:#0a1422!important;border-right:1px solid var(--border);}
h1,h2,h3{font-family:'Syne',sans-serif!important;}
[data-testid="metric-container"]{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px!important;box-shadow:0 4px 24px rgba(0,0,0,.3);}
[data-testid="metric-container"] label{color:var(--muted)!important;font-size:12px!important;text-transform:uppercase;letter-spacing:1px;}
[data-testid="metric-container"] [data-testid="stMetricValue"]{color:var(--teal)!important;font-family:'Syne',sans-serif;font-size:2rem!important;font-weight:800;}
[data-testid="stTabs"] button{font-family:'Syne',sans-serif!important;font-weight:600;color:var(--muted)!important;}
[data-testid="stTabs"] button[aria-selected="true"]{color:var(--teal)!important;border-bottom:2px solid var(--teal)!important;background:rgba(0,180,216,.08)!important;}
.dash-header{background:linear-gradient(135deg,#0d2137,#0f3460,#1a1a5e);border:1px solid var(--border);border-radius:16px;padding:26px 36px;margin-bottom:24px;display:flex;align-items:center;justify-content:space-between;box-shadow:0 8px 32px rgba(0,0,0,.4);}
.dash-header h1{margin:0;font-size:1.9rem;font-weight:800;background:linear-gradient(90deg,#00b4d8,#06d6a0);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.dash-header .sub{color:var(--muted);font-size:12px;margin-top:4px;}
.badge{padding:6px 14px;border-radius:20px;font-size:12px;font-weight:700;font-family:'Syne',sans-serif;}
.badge.live{background:rgba(6,214,160,.15);border:1px solid var(--mint);color:var(--mint);animation:blink 2s infinite;}
.badge.watch{background:rgba(0,180,216,.15);border:1px solid var(--teal);color:var(--teal);animation:blink 1.5s infinite;}
.badge.off{background:rgba(239,71,111,.1);border:1px solid var(--coral);color:var(--coral);}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.5}}
.slabel{font-family:'Syne',sans-serif;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:var(--muted);margin:18px 0 6px 0;}
.change-banner{background:rgba(6,214,160,.12);border:1px solid var(--mint);border-radius:10px;padding:10px 16px;color:var(--mint);font-size:13px;margin-bottom:14px;font-weight:600;}
.upload-hint{background:var(--card);border:2px dashed var(--border);border-radius:14px;padding:48px 20px;text-align:center;color:var(--muted);}
.upload-hint .ico{font-size:52px;display:block;margin-bottom:14px;}
.upload-hint h3{font-family:'Syne',sans-serif;color:var(--text);margin:8px 0 4px;}
.upload-hint p{font-size:13px;margin:0;}
.status-bar{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:8px 14px;font-size:12px;color:var(--muted);display:flex;justify-content:space-between;}
</style>
""", unsafe_allow_html=True)

# ── SESSION STATE INIT ────────────────────────────────────────────────────────
for k,v in [("file_bytes",None),("file_hash",""),("file_name",""),
            ("last_changed","Never"),("change_count",0),("last_poll",0)]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── FILE HASH ─────────────────────────────────────────────────────────────────
def md5(path):
    h = hashlib.md5()
    with open(path,"rb") as f: h.update(f.read())
    return h.hexdigest()

def bytes_hash(b):
    return hashlib.md5(b).hexdigest()

# ── SHEET LOADER (cached by content hash) ────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_sheets(content_hash: str, file_bytes: bytes) -> dict:
    """Cache key includes content hash — stale cache auto-busted on file change."""
    xf = pd.ExcelFile(BytesIO(file_bytes))
    out = {}
    for name in xf.sheet_names:
        if name == "INDEX": continue
        df = xf.parse(name)
        keep = [c for c in KEEP_COLS.get(name, df.columns) if c in df.columns]
        out[name] = df[keep] if keep else df
    return out

# ── POLL LOCAL FILE ───────────────────────────────────────────────────────────
def poll_local_file():
    """Check if local file changed. Returns True if updated."""
    if not LOCAL_FILE or not os.path.exists(LOCAL_FILE):
        return False
    now = time.time()
    if now - st.session_state.last_poll < POLL_SECONDS:
        return False
    st.session_state.last_poll = now
    new_hash = md5(LOCAL_FILE)
    if new_hash != st.session_state.file_hash:
        new_bytes = open(LOCAL_FILE,"rb").read()
        st.session_state.file_bytes    = new_bytes
        st.session_state.file_hash     = new_hash
        st.session_state.file_name     = os.path.basename(LOCAL_FILE)
        st.session_state.last_changed  = datetime.now().strftime("%H:%M:%S")
        st.session_state.change_count += 1
        return True
    return False

# ── AUTO-RERUN via fragment ───────────────────────────────────────────────────
# This tiny fragment re-runs every POLL_SECONDS independently of the main app,
# so the main UI only re-renders when there is an actual file change.
@st.fragment(run_every=POLL_SECONDS)
def file_watcher_fragment():
    if LOCAL_FILE and os.path.exists(LOCAL_FILE):
        new_hash = md5(LOCAL_FILE)
        if new_hash != st.session_state.file_hash:
            st.session_state.file_bytes    = open(LOCAL_FILE,"rb").read()
            st.session_state.file_hash     = new_hash
            st.session_state.file_name     = os.path.basename(LOCAL_FILE)
            st.session_state.last_changed  = datetime.now().strftime("%H:%M:%S")
            st.session_state.change_count += 1
            st.rerun()   # trigger full app rerun on change

# ── HELPERS ───────────────────────────────────────────────────────────────────
def pct_num(s):
    return pd.to_numeric(s.astype(str).str.replace("%","",regex=False).str.strip(), errors="coerce")

def filt(df, sel_col, sel_br):
    if sel_col and "College" in df.columns: df = df[df["College"].isin(sel_col)]
    if sel_br  and "Branch"  in df.columns: df = df[df["Branch"].isin(sel_br)]
    return df.reset_index(drop=True)

C = dict(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")

def hbar(df,x,y,h=270,cs=None):
    fig = px.bar(df,x=x,y=y,orientation="h",color=x,
                 color_continuous_scale=cs or ["#ef476f","#ffb703","#06d6a0"],template="plotly_dark")
    fig.update_layout(**C,coloraxis_showscale=False,margin=dict(l=0,r=0,t=8,b=0),height=h)
    return fig

def vbar(df,x,y,h=260,cs=None,angle=0):
    fig = px.bar(df,x=x,y=y,color=y,
                 color_continuous_scale=cs or ["#0f3460","#1a73e8","#06d6a0"],template="plotly_dark")
    fig.update_layout(**C,coloraxis_showscale=False,margin=dict(l=0,r=0,t=8,b=0),height=h)
    if angle: fig.update_xaxes(tickangle=angle)
    return fig

def donut(df,names,values,h=270,cs=None):
    fig = px.pie(df,names=names,values=values,hole=0.52,
                 color_discrete_sequence=cs or ["#1a73e8","#00b4d8","#06d6a0","#ffb703","#ef476f"],
                 template="plotly_dark")
    fig.update_layout(**C,margin=dict(l=0,r=0,t=8,b=0),height=h,
                      legend=dict(font=dict(color="#e8f0fe")))
    return fig

def hist_fig(df,x,h=270,cs="#1a73e8",vlines=None):
    fig = px.histogram(df,x=x,nbins=22,color_discrete_sequence=[cs],
                       template="plotly_dark",labels={x:x})
    if vlines:
        for v,col,lbl in vlines:
            fig.add_vline(x=v,line_dash="dash",line_color=col,
                          annotation_text=lbl,annotation_font_color=col)
    fig.update_layout(**C,margin=dict(t=8,b=0),height=h)
    return fig

def search_df(df,q):
    if not q: return df
    return df[df.apply(lambda r: r.astype(str).str.contains(q,case=False).any(),axis=1)]

# ── START WATCHER ─────────────────────────────────────────────────────────────
file_watcher_fragment()

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<p class="slabel">📂 Data Source</p>', unsafe_allow_html=True)

    if LOCAL_FILE:
        if os.path.exists(LOCAL_FILE):
            st.success(f"👁 Watching file every {POLL_SECONDS}s")
            st.code(os.path.basename(LOCAL_FILE), language=None)
            if st.session_state.change_count > 0:
                st.info(f"🔄 Updated {st.session_state.change_count}× · last at {st.session_state.last_changed}")
        else:
            st.error(f"❌ File not found:\n{LOCAL_FILE}")
    else:
        st.caption("💡 Set `LOCAL_FILE` in the script for auto live-updates")

    up = st.file_uploader("Or upload .xlsx manually", type=["xlsx"])
    if up:
        nb = up.read()
        nh = bytes_hash(nb)
        if nh != st.session_state.file_hash:
            st.session_state.file_bytes   = nb
            st.session_state.file_hash    = nh
            st.session_state.file_name    = up.name
            st.session_state.last_changed = datetime.now().strftime("%H:%M:%S")
            st.session_state.change_count += 1

    st.markdown("---")
    st.markdown('<p class="slabel">🖥 View</p>', unsafe_allow_html=True)
    active_tab = st.selectbox("", ["Overview","Faculty Details","Student Details",
                                   "Faculty Attendance","Student Attendance","Student Marks"],
                              label_visibility="collapsed")

    sel_col, sel_br = [], []
    if st.session_state.file_bytes:
        sheets = load_sheets(st.session_state.file_hash, st.session_state.file_bytes)
        sd = sheets.get("Student_Details", pd.DataFrame())
        if "College" in sd.columns:
            sel_col = st.multiselect("College", sorted(sd["College"].dropna().unique()), placeholder="All")
        if "Branch"  in sd.columns:
            sel_br  = st.multiselect("Branch",  sorted(sd["Branch"].dropna().unique()),  placeholder="All")

    st.markdown("---")
    if st.session_state.file_name:
        mode = f"👁 Watching · {POLL_SECONDS}s poll" if LOCAL_FILE else "📤 Uploaded"
        st.caption(f"**{st.session_state.file_name}**  \n{mode}  \nLast change: {st.session_state.last_changed}")

# ── HEADER ────────────────────────────────────────────────────────────────────
has_file = bool(st.session_state.file_bytes)
if has_file and LOCAL_FILE:
    badge = '<div class="badge watch">👁 AUTO-WATCHING</div>'
elif has_file:
    badge = '<div class="badge live">● LOADED</div>'
else:
    badge = '<div class="badge off">○ NO FILE</div>'

st.markdown(f"""
<div class="dash-header">
  <div>
    <h1>🎓 College Management Dashboard</h1>
    <div class="sub">Academic Year 2024–25 · Live File Watcher · No API Required</div>
  </div>
  {badge}
</div>""", unsafe_allow_html=True)

# ── CHANGE NOTIFICATION BANNER ────────────────────────────────────────────────
if st.session_state.change_count > 0:
    st.markdown(
        f'<div class="change-banner">✅ Dashboard updated {st.session_state.change_count} time(s) · '
        f'Last change detected at <b>{st.session_state.last_changed}</b></div>',
        unsafe_allow_html=True
    )

# ── NO FILE ───────────────────────────────────────────────────────────────────
if not has_file:
    st.markdown("""
    <div class="upload-hint">
      <span class="ico">📊</span>
      <h3>No data loaded yet</h3>
      <p>Either set <code>LOCAL_FILE</code> in the script for auto live-updates<br>
      or use the <b>sidebar upload</b> to load your Excel manually.</p>
      <br>
      <p style="font-size:12px;opacity:.7">
        ✅ No Google API &nbsp;·&nbsp; ✅ No credentials &nbsp;·&nbsp;
        ✅ Auto-detects file changes &nbsp;·&nbsp; ✅ 100% offline
      </p>
    </div>""", unsafe_allow_html=True)
    st.stop()

sheets = load_sheets(st.session_state.file_hash, st.session_state.file_bytes)
def g(n): return filt(sheets.get(n, pd.DataFrame()), sel_col, sel_br)

# ══════════════════════════════════════════════════════════════════════════════
# OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
if active_tab == "Overview":
    fac = g("Faculty_Details"); stu = g("Student_Details"); sat = g("Student_Attendance")
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("🏛 Colleges",  fac["College"].nunique() if "College" in fac.columns else 0)
    c2.metric("🌿 Branches",  fac["Branch"].nunique()  if "Branch"  in fac.columns else 0)
    c3.metric("👨‍🏫 Faculty",   len(fac))
    c4.metric("🎓 Students",   len(stu))
    avg = pct_num(sat["Total %"]).mean() if "Total %" in sat.columns else None
    c5.metric("📅 Avg Attend", f"{avg:.1f}%" if avg else "N/A")
    st.markdown("---")
    l,r = st.columns(2)
    with l:
        if "Branch" in stu.columns:
            st.markdown('<p class="slabel">Students per Branch</p>', unsafe_allow_html=True)
            b = stu["Branch"].value_counts().reset_index(); b.columns=["Branch","Count"]
            st.plotly_chart(hbar(b,"Count","Branch"), use_container_width=True)
    with r:
        if "Total %" in sat.columns:
            st.markdown('<p class="slabel">Attendance Breakdown</p>', unsafe_allow_html=True)
            pct = pct_num(sat["Total %"]).dropna()
            bc  = pd.cut(pct,[0,60,75,85,100],labels=["<60%","60-75%","75-85%","85%+"])\
                    .value_counts().reset_index(); bc.columns=["Range","Count"]
            st.plotly_chart(donut(bc,"Range","Count",cs=["#ef476f","#ffb703","#1a73e8","#06d6a0"]), use_container_width=True)
    l2,r2 = st.columns(2)
    with l2:
        if "Year" in stu.columns:
            st.markdown('<p class="slabel">Students by Year</p>', unsafe_allow_html=True)
            yr = stu["Year"].value_counts().reindex(["FE","SE","TE","BE"]).reset_index(); yr.columns=["Year","Count"]
            st.plotly_chart(vbar(yr,"Year","Count"), use_container_width=True)
    with r2:
        if "Designation" in fac.columns:
            st.markdown('<p class="slabel">Faculty by Designation</p>', unsafe_allow_html=True)
            des = fac["Designation"].value_counts().reset_index(); des.columns=["Designation","Count"]
            st.plotly_chart(donut(des,"Designation","Count"), use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# FACULTY DETAILS
# ══════════════════════════════════════════════════════════════════════════════
elif active_tab == "Faculty Details":
    df = g("Faculty_Details")
    c1,c2,c3 = st.columns(3)
    c1.metric("Total Faculty", len(df))
    if "College" in df.columns: c2.metric("Colleges", df["College"].nunique())
    if "Branch"  in df.columns: c3.metric("Branches", df["Branch"].nunique())
    if "Designation" in df.columns:
        st.markdown('<p class="slabel">By Designation</p>', unsafe_allow_html=True)
        des = df["Designation"].value_counts().reset_index(); des.columns=["Designation","Count"]
        st.plotly_chart(vbar(des,"Designation","Count",h=240,cs=["#1a73e8","#06d6a0"]), use_container_width=True)
    st.markdown('<p class="slabel">Faculty Table</p>', unsafe_allow_html=True)
    st.dataframe(search_df(df, st.text_input("🔍 Search name / ID")), use_container_width=True, height=420)

# ══════════════════════════════════════════════════════════════════════════════
# STUDENT DETAILS
# ══════════════════════════════════════════════════════════════════════════════
elif active_tab == "Student Details":
    df = g("Student_Details")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total Students", len(df))
    if "College" in df.columns: c2.metric("Colleges", df["College"].nunique())
    if "Branch"  in df.columns: c3.metric("Branches", df["Branch"].nunique())
    if "Year"    in df.columns: c4.metric("Year Groups", df["Year"].nunique())
    l,r = st.columns(2)
    with l:
        if "Branch" in df.columns:
            st.markdown('<p class="slabel">Students per Branch</p>', unsafe_allow_html=True)
            b = df["Branch"].value_counts().reset_index(); b.columns=["Branch","Count"]
            st.plotly_chart(vbar(b,"Branch","Count",angle=30), use_container_width=True)
    with r:
        if "Div" in df.columns:
            st.markdown('<p class="slabel">Division Split</p>', unsafe_allow_html=True)
            d = df["Div"].value_counts().reset_index(); d.columns=["Div","Count"]
            st.plotly_chart(donut(d,"Div","Count",cs=["#00b4d8","#06d6a0","#1a73e8"]), use_container_width=True)
    st.markdown('<p class="slabel">Student Table</p>', unsafe_allow_html=True)
    st.dataframe(search_df(df, st.text_input("🔍 Search roll / name")), use_container_width=True, height=420)

# ══════════════════════════════════════════════════════════════════════════════
# FACULTY ATTENDANCE
# ══════════════════════════════════════════════════════════════════════════════
elif active_tab == "Faculty Attendance":
    df = g("Faculty_Attendance").copy()
    if "Total %" in df.columns:
        df["_p"] = pct_num(df["Total %"])
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Faculty",len(df)); c2.metric("Avg",f"{df['_p'].mean():.1f}%")
        c3.metric("✅ ≥75%",int((df["_p"]>=75).sum())); c4.metric("⚠️ <75%",int((df["_p"]<75).sum()))
        l,r = st.columns(2)
        with l:
            st.markdown('<p class="slabel">Distribution</p>', unsafe_allow_html=True)
            st.plotly_chart(hist_fig(df,"_p",cs="#00b4d8",vlines=[(75,"#ef476f","75%")]), use_container_width=True)
        with r:
            if "Branch" in df.columns:
                st.markdown('<p class="slabel">Avg by Branch</p>', unsafe_allow_html=True)
                br = df.groupby("Branch")["_p"].mean().reset_index().sort_values("_p"); br.columns=["Branch","Avg %"]
                st.plotly_chart(hbar(br,"Avg %","Branch"), use_container_width=True)
        df.drop(columns=["_p"], inplace=True)
    st.dataframe(search_df(df, st.text_input("🔍 Search name")), use_container_width=True, height=420)

# ══════════════════════════════════════════════════════════════════════════════
# STUDENT ATTENDANCE
# ══════════════════════════════════════════════════════════════════════════════
elif active_tab == "Student Attendance":
    df = g("Student_Attendance").copy()
    if "Total %" in df.columns:
        df["_p"] = pct_num(df["Total %"])
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Students",len(df)); c2.metric("Avg",f"{df['_p'].mean():.1f}%")
        c3.metric("✅ ≥75%",int((df["_p"]>=75).sum())); c4.metric("🚨 <60%",int((df["_p"]<60).sum()))
        l,r = st.columns(2)
        with l:
            st.markdown('<p class="slabel">Distribution</p>', unsafe_allow_html=True)
            st.plotly_chart(hist_fig(df,"_p",cs="#1a73e8",
                            vlines=[(75,"#ffb703","75%"),(60,"#ef476f","60%")]), use_container_width=True)
        with r:
            if "Year" in df.columns:
                st.markdown('<p class="slabel">Avg by Year</p>', unsafe_allow_html=True)
                yr = df.groupby("Year")["_p"].mean().reindex(["FE","SE","TE","BE"]).reset_index(); yr.columns=["Year","Avg %"]
                st.plotly_chart(vbar(yr,"Year","Avg %",cs=["#0f3460","#1a73e8","#06d6a0"]), use_container_width=True)
        df.drop(columns=["_p"], inplace=True)
    st.dataframe(search_df(df, st.text_input("🔍 Search roll / name")), use_container_width=True, height=420)

# ══════════════════════════════════════════════════════════════════════════════
# STUDENT MARKS
# ══════════════════════════════════════════════════════════════════════════════
elif active_tab == "Student Marks":
    df = g("Student_Marks").copy()
    gt = next((c for c in df.columns if "Grand" in c or "Total" in c.title()), None)
    if gt:
        df["Grand Total"] = pd.to_numeric(df[gt], errors="coerce")
        if gt != "Grand Total": df.drop(columns=[gt], inplace=True)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Students", len(df))
    if "Grand Total" in df.columns and not df.empty:
        c2.metric("Avg Score",f"{df['Grand Total'].mean():.1f}")
        c3.metric("Highest",  int(df["Grand Total"].max()))
        c4.metric("Lowest",   int(df["Grand Total"].min()))
    l,r = st.columns(2)
    with l:
        if "Grand Total" in df.columns:
            st.markdown('<p class="slabel">Score Distribution</p>', unsafe_allow_html=True)
            st.plotly_chart(hist_fig(df,"Grand Total",cs="#06d6a0"), use_container_width=True)
    with r:
        if "Branch" in df.columns and "Grand Total" in df.columns:
            st.markdown('<p class="slabel">Avg Score by Branch</p>', unsafe_allow_html=True)
            br = df.groupby("Branch")["Grand Total"].mean().reset_index().sort_values("Grand Total"); br.columns=["Branch","Avg Score"]
            st.plotly_chart(hbar(br,"Avg Score","Branch"), use_container_width=True)
    if "Grand Total" in df.columns:
        st.markdown('<p class="slabel">Grade Bands (out of 185)</p>', unsafe_allow_html=True)
        labels = ["F <40%","D 40-49%","C 50-59%","B 60-79%","A 80-100%"]
        df["Grade"] = pd.cut(df["Grand Total"],[0,74,92,111,148,185],labels=labels)
        gb = df["Grade"].value_counts().reindex(labels).reset_index(); gb.columns=["Grade","Count"]
        fig = px.bar(gb,x="Grade",y="Count",color="Grade",template="plotly_dark",
                     color_discrete_map={"F <40%":"#ef476f","D 40-49%":"#ffb703",
                                         "C 50-59%":"#1a73e8","B 60-79%":"#00b4d8","A 80-100%":"#06d6a0"})
        fig.update_layout(**C,showlegend=False,margin=dict(t=5,b=0),height=240)
        st.plotly_chart(fig, use_container_width=True)
        df.drop(columns=["Grade"], inplace=True)
    st.dataframe(search_df(df, st.text_input("🔍 Search roll / name")), use_container_width=True, height=420)
