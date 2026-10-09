from __future__ import annotations

import hashlib
import html
import os
from datetime import datetime, timedelta
from decimal import Decimal

import streamlit as st

from rechnungsklar.exports import build_review_bundle, inbox_csv
from rechnungsklar.models import InvoiceRecord
from rechnungsklar.parser import InvoiceParseError, parse_invoice_file
from rechnungsklar.validation import Finding, pdf_review_hints, run_validation


st.set_page_config(
    page_title="Rechnungsklar — E-Rechnungsarbeitsplatz",
    page_icon="R",
    layout="wide",
    initial_sidebar_state="expanded",
)

MAX_UPLOAD_MB = 20
ALLOWED_EXTENSIONS = {".xml", ".pdf"}
# Keep public portfolio deployments safe by default. Enable real uploads only
# after authentication, tenant isolation, and private persistent storage exist.
PORTFOLIO_DEMO_MODE = True
STATES = ["Neu", "In Prüfung", "Rückfrage nötig", "Freigegeben", "Abgelehnt"]
STATE_META = {
    "Neu": ("new", "Neu"),
    "In Prüfung": ("review", "In Prüfung"),
    "Rückfrage nötig": ("attention", "Rückfrage nötig"),
    "Freigegeben": ("approved", "Freigegeben"),
    "Abgelehnt": ("rejected", "Abgelehnt"),
}


st.markdown(
    """
    <style>
    :root {
      --ink:#172b25; --forest:#123e31; --forest2:#1b5e47; --mint:#eaf3ed;
      --paper:#fffefa; --canvas:#f3f5f1; --line:#e4e9e3; --muted:#738078;
      --lime:#d7ef8b; --amber:#e6a53b; --red:#bf594d; --shadow:0 14px 38px rgba(26,48,37,.055);
    }
    html,body,[class*="css"] { font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }
    .stApp { background:var(--canvas); color:var(--ink); }
    [data-testid="stHeader"] { background:transparent; }
    .block-container { max-width:1580px; padding-top:1.8rem; padding-bottom:3rem; }
    [data-testid="stSidebar"] { background:#fbfcfa; border-right:1px solid var(--line); }
    [data-testid="stSidebar"] > div:first-child { padding:1.2rem 1rem 1rem; }
    h1,h2,h3,p { color:var(--ink); }
    h1 { font-size:2.25rem !important; line-height:1.08 !important; font-weight:750 !important; letter-spacing:-.055em !important; }
    h2 { font-size:1.38rem !important; font-weight:720 !important; letter-spacing:-.035em !important; }
    h3 { font-size:1.02rem !important; font-weight:700 !important; letter-spacing:-.02em !important; }
    [data-testid="stVerticalBlock"] { gap:.85rem; }
    [data-testid="stHorizontalBlock"] { gap:1rem; }
    [data-testid="stFileUploaderDropzone"] { background:#fff; border:1px dashed #aebdb1; border-radius:14px; min-height:90px; }
    [data-testid="stFileUploaderDropzone"]:hover { border-color:var(--forest2); background:#fbfdfb; }
    [data-testid="stFileUploaderDropzoneInstructions"] small { color:var(--muted); }
    .stButton button,.stDownloadButton button { border-radius:10px; border-color:#dce4dd; font-weight:650; min-height:2.45rem; transition:all .15s ease; }
    .stButton button[kind="primary"],.stDownloadButton button[kind="primary"] { background:var(--forest); border-color:var(--forest); color:#fff; }
    .stButton button:hover,.stDownloadButton button:hover { border-color:var(--forest2); color:var(--forest2); }
    .stButton button[kind="primary"]:hover,.stDownloadButton button[kind="primary"]:hover { background:var(--forest2); color:white; }
    [data-testid="stTextInput"] input,[data-testid="stSelectbox"] div[data-baseweb="select"] { border-radius:10px; }
    [data-testid="stForm"] { border:0; padding:0; }
    [data-testid="stContainer"] { border-radius:16px; }
    div[data-testid="stMarkdownContainer"] p { line-height:1.55; }
    .brand { display:flex; gap:11px; align-items:center; padding:5px 4px 25px; }
    .brand-icon { width:38px;height:38px;border-radius:13px;background:var(--forest);color:#eaf2cf;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:850;box-shadow:0 5px 12px #123e3125; }
    .brand-name { font-size:17px;font-weight:800;letter-spacing:-.045em;color:var(--ink); }
    .brand-caption { color:var(--muted);font-size:10px;letter-spacing:.12em;text-transform:uppercase;margin-top:1px; }
    .nav-label,.eyebrow { color:#829087;font-size:10px;font-weight:800;letter-spacing:.14em;text-transform:uppercase; }
    .eyebrow { margin-bottom:8px; }
    .hero-copy { color:var(--muted);font-size:15px;margin-top:-3px; }
    .hero-meta { color:#7b8980;font-size:12px;margin-top:12px; }
    .badge { display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:6px 10px;font-size:11px;font-weight:750;white-space:nowrap; }
    .badge-dot { width:6px;height:6px;border-radius:50%;background:currentColor; }
    .badge-new { background:#eef1ee;color:#617168; }
    .badge-review { background:#eaf0ff;color:#5369a6; }
    .badge-attention { background:#fff2db;color:#9a681b; }
    .badge-approved { background:#e6f4ea;color:#32734b; }
    .badge-rejected { background:#fbe9e7;color:#a54d45; }
    .stat-card { min-height:114px;background:white;border:1px solid var(--line);border-radius:16px;padding:16px 18px;box-shadow:var(--shadow); }
    .stat-top { display:flex;justify-content:space-between;align-items:center;color:#77857c;font-size:11px;font-weight:650; }
    .stat-icon { width:28px;height:28px;display:flex;align-items:center;justify-content:center;border-radius:9px;background:#f0f4ed;color:var(--forest2);font-weight:800; }
    .stat-value { margin-top:9px;color:var(--ink);font-size:27px;font-weight:780;letter-spacing:-.055em;line-height:1.1; }
    .stat-note { color:#87938b;font-size:11px;margin-top:4px; }
    .section-title { display:flex;align-items:baseline;justify-content:space-between; }
    .section-title small { color:#8a958d;font-size:11px; }
    .avatar { display:flex;align-items:center;justify-content:center;width:39px;height:39px;border-radius:13px;background:#e8f0e8;color:#285a42;font-weight:800;font-size:12px;letter-spacing:-.03em; }
    .avatar.a1 { background:#f4e9dc;color:#815631; }
    .avatar.a2 { background:#e7eaf5;color:#4c5f8b; }
    .avatar.a3 { background:#f4e7e7;color:#8b5551; }
    .queue-name { font-size:13px;font-weight:750;color:var(--ink);line-height:1.25; }
    .queue-id { color:#849087;font-size:10px;margin-top:4px; }
    .queue-amount { font-size:13px;font-weight:750;letter-spacing:-.025em;text-align:right;color:var(--ink); }
    .queue-date { text-align:right;color:#89948d;font-size:10px;margin-top:4px; }
    .invoice-paper { position:relative;background:var(--paper);border:1px solid #e8e7df;border-radius:17px;padding:25px 27px;box-shadow:0 12px 35px rgba(54,58,44,.06);overflow:hidden; }
    .invoice-paper:before { content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:#c8dc9d; }
    .paper-top { display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #ecece5;padding-bottom:15px;margin-bottom:18px; }
    .paper-logo { font-size:11px;font-weight:800;letter-spacing:.12em;color:#597363;text-transform:uppercase; }
    .paper-ref { color:#99a39a;font-size:10px; }
    .paper-seller { font-size:21px;font-weight:780;letter-spacing:-.045em;color:var(--ink);line-height:1.2; }
    .paper-sub { color:#77847b;font-size:12px;margin-top:5px; }
    .paper-meta { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px 22px;padding:20px 0;border-bottom:1px solid #ecece5; }
    .paper-label { color:#89948b;font-size:9px;font-weight:800;letter-spacing:.11em;text-transform:uppercase;margin-bottom:5px; }
    .paper-value { color:#273830;font-size:12px;font-weight:650;overflow-wrap:anywhere; }
    .line-heading { display:flex;justify-content:space-between;color:#8a968d;font-size:9px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;padding:16px 0 9px; }
    .line-row { display:flex;justify-content:space-between;gap:12px;border-top:1px solid #f0f0ea;padding:12px 0;color:#33433a;font-size:12px; }
    .line-desc { font-weight:630; }
    .line-detail { color:#879188;font-size:10px;margin-top:3px; }
    .line-amount { font-weight:700;white-space:nowrap; }
    .paper-totals { width:min(100%,280px);margin:16px 0 0 auto;padding-top:13px;border-top:1px solid #e7e8df; }
    .total-row { display:flex;justify-content:space-between;gap:16px;color:#728077;font-size:11px;padding:4px 0; }
    .total-row strong { color:#304238;font-weight:700; }
    .total-due { display:flex;justify-content:space-between;gap:16px;align-items:baseline;margin-top:9px;padding-top:11px;border-top:1px solid #e6e8de;color:var(--forest);font-size:12px;font-weight:800; }
    .total-due span:last-child { font-size:20px;letter-spacing:-.04em; }
    .mini-card { background:#fff;border:1px solid var(--line);border-radius:14px;padding:15px 16px; }
    .mini-label { color:#859188;font-size:10px;font-weight:800;letter-spacing:.1em;text-transform:uppercase; }
    .mini-value { color:#273930;font-size:13px;font-weight:700;margin-top:5px;overflow-wrap:anywhere; }
    .check-row { display:flex;gap:10px;padding:10px 0;border-bottom:1px solid #edf0eb; }
    .check-row:last-child { border-bottom:0; }
    .check-icon { flex:none;width:23px;height:23px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:800; }
    .check-icon.error { background:#fff0de;color:#a76b1a; }
    .check-icon.warning { background:#fff5df;color:#a57824; }
    .check-icon.info { background:#eaf2ec;color:#3e7955; }
    .check-title { color:#34443b;font-size:11px;font-weight:750; }
    .check-copy { color:#7a877e;font-size:10px;line-height:1.45;margin-top:3px; }
    .progress-track { display:flex;align-items:center;gap:7px;margin:2px 0 17px; }
    .progress-step { display:flex;align-items:center;gap:6px;color:#748179;font-size:10px;font-weight:650;white-space:nowrap; }
    .progress-num { display:flex;align-items:center;justify-content:center;width:19px;height:19px;border-radius:50%;background:#eaf0e9;color:#41624c;font-size:9px;font-weight:800; }
    .progress-step.active { color:#315a42; }
    .progress-step.active .progress-num { background:var(--forest);color:white; }
    .progress-line { flex:1;height:1px;background:#dce4dc;min-width:12px; }
    .empty-state { padding:35px 22px;text-align:center;border:1px dashed #c7d1c8;border-radius:18px;background:#fbfcfa; }
    .empty-icon { width:52px;height:52px;margin:0 auto 14px;border-radius:17px;background:#eaf2e9;color:#2c6548;display:flex;align-items:center;justify-content:center;font-size:23px; }
    .empty-title { color:var(--ink);font-size:17px;font-weight:780;letter-spacing:-.035em; }
    .empty-copy { max-width:410px;margin:7px auto 0;color:#7d8980;font-size:12px;line-height:1.6; }
    .sidebar-panel { background:#f2f6f1;border:1px solid #e6ece4;border-radius:13px;padding:13px;margin:8px 0; }
    .sidebar-panel-title { color:#738078;font-size:9px;font-weight:800;letter-spacing:.12em;text-transform:uppercase; }
    .sidebar-panel-value { color:#284437;font-size:12px;font-weight:700;margin-top:6px; }
    .sidebar-panel-copy { color:#859088;font-size:10px;line-height:1.45;margin-top:4px; }
    .fineprint { color:#87928a;font-size:10px;line-height:1.5; }
    .upload-caption { color:#839087;font-size:10px;margin-top:-5px; }
    .rule-pill { display:inline-block;border-radius:7px;background:#f0f3ee;color:#718078;font-size:9px;font-weight:700;padding:4px 7px;margin:2px 3px 2px 0; }
    .page-title{margin:0!important;font-size:2.5rem!important;letter-spacing:-.06em!important;line-height:1.05!important}.page-subtitle{color:var(--muted);font-size:14px;margin:9px 0 22px;max-width:760px}
    .hero-shell{display:grid;grid-template-columns:1.45fr .75fr;gap:22px;min-height:260px;padding:30px 34px;background:radial-gradient(circle at 82% 30%,#2c7056 0,#1a513f 30%,#10392e 75%);border:1px solid #194e3c;border-radius:24px;color:white;position:relative;overflow:hidden;box-shadow:0 22px 50px #11392e29}.hero-shell:after{content:"";position:absolute;width:340px;height:340px;border:1px solid #ddf2ae21;border-radius:50%;right:8%;top:-190px;box-shadow:0 0 0 28px #ddf2ae09,0 0 0 62px #ddf2ae08}
    .hero-shell>div{position:relative;z-index:1}.hero-kicker{color:#c4d9c9;font-size:9px;font-weight:800;letter-spacing:.16em}.live-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#c9ec8c;margin-right:8px}.hero-title{margin-top:18px;color:white;font-size:37px;font-weight:780;letter-spacing:-.06em;line-height:1.02}.hero-copy{color:#d1e0d6;font-size:13px;line-height:1.65;max-width:540px;margin-top:14px}.hero-tags{display:flex;gap:8px;margin-top:18px}.hero-tags span{border:1px solid #e8f4e738;background:#fafff912;color:#e7f2e8;padding:6px 10px;border-radius:999px;font-size:9px;font-weight:700}
    .hero-side{display:flex;flex-direction:column;align-items:center;justify-content:center}.hero-date{align-self:flex-end;color:#bed1c3;font-size:10px}.hero-orbit{position:relative;display:flex;align-items:center;justify-content:center;width:160px;height:160px;border:1px solid #e9f6e82e;border-radius:50%;box-shadow:0 0 0 15px #ecf6e909,0 0 0 31px #ecf6e906;margin:8px 0}.orbit-core{display:flex;flex-direction:column;align-items:center;justify-content:center;width:88px;height:88px;border-radius:50%;background:linear-gradient(145deg,#e3f2bb,#c8e78b);color:#173b2d}.orbit-core strong{font-size:31px;line-height:1}.orbit-core span{font-size:9px;font-weight:800;text-transform:uppercase}.orbit-label{position:absolute;padding:5px 8px;border:1px solid #e7f6e938;background:#1b5641;color:#e4f0e3;border-radius:99px;font-size:8px}.label-one{top:13px;left:0}.label-two{right:-20px;top:65px}.label-three{bottom:9px;left:14px}.hero-side-caption{color:#bfd1c4;font-size:9px}.privacy-inline{color:#829087;font-size:10px;padding:8px 3px}
    .dashboard-heading{display:flex;align-items:flex-end;justify-content:space-between;margin:16px 0 10px}.dashboard-heading h2{font-size:18px!important;margin:0!important}.dashboard-heading .eyebrow{margin-bottom:5px}.subtle-count{color:#8a958d;font-size:10px}
    .focus-row{display:flex;align-items:center;gap:11px;padding:13px;background:#fff;border:1px solid #e7ece6;border-radius:14px;margin:8px 0;box-shadow:0 5px 17px #182d2206}.focus-icon{width:31px;height:31px;display:flex;align-items:center;justify-content:center;border-radius:10px;font-weight:800}.tone-attention{color:#9a6419;background:#fff1d9}.tone-review{color:#4f658d;background:#edf1fb}.focus-main{min-width:0;flex:1}.focus-name{color:#263930;font-size:11px;font-weight:750}.focus-meta{color:#89948c;font-size:9px;margin-top:4px}.focus-end{text-align:right;white-space:nowrap}.focus-amount{color:#263930;font-size:11px;font-weight:750}.focus-state{color:#89948c;font-size:9px;margin-top:4px}
    .calm-empty,.chart-empty{display:flex;align-items:center;gap:13px;padding:20px 17px;border:1px dashed #cad5cb;border-radius:16px;background:#fbfcfa;color:#78857c;font-size:11px;line-height:1.55}.calm-empty>span{width:33px;height:33px;display:grid;place-items:center;border-radius:11px;background:#e9f1e8;color:#32654a;font-size:16px}.calm-empty strong{color:#33473b}
    .spend-row{margin:15px 0}.spend-top{display:flex;justify-content:space-between;gap:10px;color:#34453b;font-size:10px}.spend-top span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.spend-track{height:6px;margin-top:7px;background:#e9eee8;border-radius:99px;overflow:hidden}.spend-fill{height:100%;border-radius:99px;background:linear-gradient(90deg,#285c43,#91b86e)}
    .standard-note{display:flex;gap:10px;margin-top:20px;padding:12px;border:1px solid #e5ece4;border-radius:13px;background:#f9fbf7}.standard-icon{width:24px;height:24px;display:grid;place-items:center;border-radius:8px;background:#e5f0e2;color:#437153}.standard-note strong,.standard-note span{display:block}.standard-note strong{color:#3c5144;font-size:10px}.standard-note span{color:#87928a;font-size:9px;margin-top:3px}
    .recent-row{display:flex;align-items:center;gap:11px;padding:11px 2px;border-bottom:1px solid #e8ece7}.recent-mark{width:8px;height:8px;border-radius:50%;background:#87a976}.recent-text{min-width:0;flex:1}.recent-text strong,.recent-text span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.recent-text strong{color:#33443a;font-size:10px}.recent-text span{color:#8a958d;font-size:9px;margin-top:4px}.recent-amount{font-size:10px;font-weight:750;white-space:nowrap}
    .product-card{background:#eef3e9;border:1px solid #e2e9dd;border-radius:17px;padding:20px}.product-card-title{color:#244133;font-size:19px;font-weight:760;line-height:1.2}.product-card p{color:#748178;font-size:10px;line-height:1.55}.workflow-mini{display:flex;align-items:center;gap:8px;margin-top:18px}.workflow-mini div{display:flex;align-items:center;gap:5px;color:#45624d;font-size:8px;white-space:nowrap}.workflow-mini i{display:grid;place-items:center;width:20px;height:20px;border-radius:50%;background:#dce9d4;font-style:normal}.workflow-mini b{height:1px;flex:1;background:#cfdcc9}
    .upload-head{display:flex;align-items:center;justify-content:space-between;padding-bottom:10px}.upload-head strong,.upload-head span{display:block}.upload-head strong{font-size:14px}.upload-head span{color:#87928a;font-size:10px;margin-top:4px}.upload-mark{display:grid;place-items:center;width:34px;height:34px;border-radius:11px;background:#eaf1e8;color:#32654a;font-size:17px}
    .info-panel{height:100%;padding:22px;background:white;border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow)}.info-panel h2{font-size:19px!important}.info-panel p{color:#78857d;font-size:11px;line-height:1.6}.compliance-step,.roadmap-item{display:flex;gap:11px;padding:13px 0;border-top:1px solid #edf0ec}.compliance-step>i,.roadmap-item>i{display:grid;place-items:center;width:24px;height:24px;flex:none;border-radius:8px;background:#edf2e9;color:#4d6d51;font-style:normal;font-size:9px}.compliance-step div,.roadmap-item div{flex:1}.compliance-step strong,.compliance-step span,.roadmap-item strong,.roadmap-item span{display:block}.compliance-step strong,.roadmap-item strong{font-size:10px}.compliance-step span,.roadmap-item span{color:#849087;font-size:9px;line-height:1.5;margin-top:4px}.compliance-step>b{font-size:8px}.setting-line{display:flex;justify-content:space-between;padding:12px 0;border-top:1px solid #edf0ec;color:#77847b;font-size:10px}.setting-line strong{color:#34463b}
    .validator-state{margin:17px 0;padding:10px;border-radius:10px;background:#f5f2e9;color:#8d7137;font-size:9px}.validator-state.connected{background:#edf5ec;color:#3f7450}.supplier-card{padding:18px;background:white;border:1px solid #e5ebe4;border-radius:17px;box-shadow:var(--shadow);margin-bottom:10px}.supplier-card-top{display:flex;align-items:center;gap:12px}.supplier-title-wrap{flex:1;min-width:0}.supplier-title-wrap strong,.supplier-title-wrap span{display:block}.supplier-title-wrap strong{font-size:12px}.supplier-title-wrap span{color:#88948b;font-size:9px;margin-top:5px}.supplier-total{font-size:12px;font-weight:780}.supplier-card-bottom{display:flex;justify-content:space-between;gap:8px;margin-top:15px;padding-top:12px;border-top:1px solid #edf0ec;color:#89948c;font-size:9px}.supplier-health{border-radius:99px;padding:5px 8px;font-size:8px;background:#edf4ec;color:#4e7a55}.supplier-health.needs-review{background:#fff3df;color:#9b6c23}
    .sidebar-panel{background:#f4f7f2;border-color:#e7ede5}.sidebar-footnote{margin-top:10px;color:#929c94;font-size:8px;line-height:1.5}.app-footer{margin-top:30px;padding-top:13px;border-top:1px solid #e4e9e3;color:#9aa39c;font-size:8px;letter-spacing:.08em}
    :root{--ink:#172b3a;--forest:#173b50;--forest2:#286d78;--mint:#e9f0f4;--paper:#fffefa;--canvas:#f3f6f8;--line:#dfe6ec;--muted:#627584;--lime:#f2c995;--amber:#ce8739;--red:#c25a4d;--shadow:0 14px 38px rgba(26,48,58,.07)}
    .stApp{background:var(--canvas);color:var(--ink)}
    [data-testid="stSidebar"]{background:#fbfcfe;border-right:1px solid #d9e2e8}
    [data-testid="stSidebar"] [data-testid="stRadio"] label{display:flex;align-items:center;width:100%;min-height:44px;padding:9px 11px!important;border:1px solid transparent;border-radius:11px;color:#2c4352!important;font-size:14px!important;font-weight:680!important;transition:background .18s ease,border-color .18s ease,transform .18s ease}
    [data-testid="stSidebar"] [data-testid="stRadio"] label *{color:inherit!important}
    [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked){background:#173b50!important;border-color:#173b50!important;color:#fff!important;box-shadow:0 7px 18px #173b5023}
    [data-testid="stSidebar"] [data-testid="stRadio"] label:hover{background:#eaf0f3;border-color:#d8e1e7;transform:translateX(2px)}
    [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked):hover{background:#205266!important;border-color:#205266!important;color:#fff!important}
    [data-testid="stSidebar"] [data-testid="stRadio"] input{accent-color:#e58c62}
    .brand-caption,.nav-label,.eyebrow{font-size:11px}
    .sidebar-panel-title{font-size:9px;color:#647781}.sidebar-panel-value{font-size:14px}.sidebar-panel-copy,.sidebar-footnote{font-size:11px;color:#657783}
    .queue-id,.queue-date,.paper-label{font-size:11px}.paper-label{color:#657783}.paper-value{font-size:13px}.line-detail{font-size:11px}
    .check-title{font-size:12px}.check-copy{font-size:11px}.mini-label{font-size:11px}.stat-note{font-size:12px}
    .hero-shell{background:radial-gradient(circle at 82% 30%,#376783 0,#205b68 34%,#153d50 78%);background-size:180% 180%;animation:ambient-shift 22s ease-in-out infinite alternate}
    .hero-title{font-size:40px}.hero-kicker{font-size:10px}.hero-tags span{font-size:10px}.hero-side-caption{font-size:10px}
    .live-dot{background:#f2b47e;box-shadow:0 0 0 4px #f2b47e2b;animation:soft-pulse 2.6s ease-in-out infinite}
    .orbit-core{background:linear-gradient(145deg,#f6dfbd,#efbd83);animation:gentle-float 5s ease-in-out infinite}
    .focus-name{font-size:12px}.focus-meta,.focus-state{font-size:10px}.focus-amount{font-size:12px}
    .spend-top{font-size:12px}.recent-text strong{font-size:11px}.recent-text span{font-size:10px}.recent-amount{font-size:11px}
    .product-card p{font-size:11px}.workflow-mini div{font-size:9px}.upload-head span{font-size:11px}
    .info-panel p{font-size:12px}.compliance-step strong,.roadmap-item strong{font-size:11px}.compliance-step span,.roadmap-item span{font-size:10px}.compliance-step>b{font-size:9px}.validator-state{font-size:11px}
    .supplier-title-wrap strong{font-size:13px}.supplier-title-wrap span,.supplier-card-bottom{font-size:10px}.supplier-total{font-size:13px}.supplier-health{font-size:9px}
    .stButton button,.stDownloadButton button{min-height:2.7rem;font-size:14px;transition:background .18s ease,border-color .18s ease,color .18s ease,transform .18s ease,box-shadow .18s ease}
    .stButton button[kind="primary"],.stDownloadButton button[kind="primary"]{position:relative;overflow:hidden;background:#173b50!important;border:1px solid #173b50!important;color:#fff!important;box-shadow:0 5px 13px #173b5025}
    .stButton button[kind="primary"] *, .stDownloadButton button[kind="primary"] *{color:#fff!important;fill:#fff!important}
    .stButton [data-testid="stBaseButton-primary"],.stDownloadButton [data-testid="stBaseButton-primary"]{background:#173b50!important;border-color:#173b50!important;color:#fff!important}
    .stButton [data-testid="stBaseButton-primary"] *, .stDownloadButton [data-testid="stBaseButton-primary"] *{color:#fff!important;fill:#fff!important}
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"]{background:#173b50!important;color:#fff!important}
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] *{color:#fff!important}
    .stButton button[kind="secondary"],.stDownloadButton button[kind="secondary"]{background:#fff!important;color:#173b50!important;border-color:#ccd9e0!important}
    .stButton button[kind="secondary"] *, .stDownloadButton button[kind="secondary"] *{color:#173b50!important;fill:#173b50!important}
    .stButton [data-testid="stBaseButton-secondary"],.stDownloadButton [data-testid="stBaseButton-secondary"]{background:#fff!important;color:#173b50!important;border-color:#ccd9e0!important}
    .stButton [data-testid="stBaseButton-secondary"] *, .stDownloadButton [data-testid="stBaseButton-secondary"] *{color:#173b50!important;fill:#173b50!important}
    .stButton button[kind="primary"]:hover,.stDownloadButton button[kind="primary"]:hover{background:#245a70!important;border-color:#245a70!important;color:#fff!important;transform:translateY(-2px);box-shadow:0 9px 20px #173b5033}
    .stButton button[kind="secondary"]:hover,.stDownloadButton button[kind="secondary"]:hover{background:#edf4f6!important;border-color:#9db8c5!important;color:#173b50!important;transform:translateY(-1px)}
    .stButton button:focus-visible,.stDownloadButton button:focus-visible{outline:3px solid #e8a276!important;outline-offset:2px}
    .stButton button[kind="primary"]:after{content:"";position:absolute;top:0;bottom:0;left:-125%;width:52%;background:linear-gradient(100deg,transparent,#ffffff35,transparent);transform:skewX(-20deg);transition:left .7s ease;pointer-events:none}
    .stButton button[kind="primary"]:hover:after{left:150%}
    .stat-card,.supplier-card,.product-card,.info-panel,.focus-row{transition:transform .22s ease,box-shadow .22s ease,border-color .22s ease}
    .stat-card:hover,.supplier-card:hover,.product-card:hover,.info-panel:hover{transform:translateY(-3px);box-shadow:0 18px 38px #173b5018;border-color:#c7d7de}
    .focus-row:hover{transform:translateX(3px);border-color:#c8d8df;box-shadow:0 9px 22px #173b5012}
    .spend-fill{transition:width .8s cubic-bezier(.2,.7,.2,1)}
    .recent-row:hover{background:#f1f6f7;border-radius:8px;padding-left:9px;padding-right:9px;transition:all .18s ease}
    @media(prefers-reduced-motion:reduce){.stButton button,.stDownloadButton button,.stat-card,.supplier-card,.product-card,.info-panel,.focus-row,.recent-row{transition:none!important}.stButton button[kind="primary"]:after{display:none}}
    .motion-banner{display:flex;align-items:center;gap:13px;overflow:hidden;margin:0 0 16px;padding:9px 12px;background:#fff;border:1px solid #dfe6ec;border-radius:12px;box-shadow:0 5px 15px #18394a0a}
    .ticker-label{flex:none;padding:5px 8px;border-radius:7px;background:#fff0e5;color:#9b573b;font-size:9px;font-weight:850;letter-spacing:.1em}
    .ticker-window{min-width:0;overflow:hidden;flex:1;mask-image:linear-gradient(90deg,transparent,#000 5%,#000 95%,transparent)}
    .ticker-track{display:flex;align-items:center;gap:25px;width:max-content;animation:ticker-slide 34s linear infinite;color:#4b6370;font-size:10px;font-weight:750;letter-spacing:.07em;white-space:nowrap}
    .ticker-track b{color:#e28e62;font-size:13px}
    .motion-banner:hover .ticker-track{animation-play-state:paused}
    .demo-mode-banner{display:flex;align-items:center;gap:12px;margin:0 0 16px;padding:12px 15px;border:1px solid #c9dce4;border-radius:13px;background:linear-gradient(105deg,#edf6f8,#fffaf3);color:#254958;box-shadow:0 7px 18px #173b500c}
    .demo-mode-icon{display:grid;place-items:center;flex:none;width:30px;height:30px;border-radius:10px;background:#dcebf0;color:#245669;font-weight:850}
    .demo-mode-copy{font-size:13px;line-height:1.45}.demo-mode-copy strong{color:#173b50}.demo-mode-copy span{color:#5e7480}
    .tour-panel{padding:12px 14px;border:1px solid #c8dce5;border-left:4px solid #e69a6e;border-radius:13px;background:#fff;box-shadow:0 8px 20px #173b500c;animation:hint-enter .35s ease both}
    .tour-panel strong{color:#183e52;font-size:14px}.tour-panel p{color:#5e7280;font-size:13px;line-height:1.5;margin:4px 0 0}
    .tour-kicker{color:#ad6746;font-size:10px;font-weight:850;letter-spacing:.1em;text-transform:uppercase;margin-bottom:4px}
    @keyframes hint-enter{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
    @media(prefers-reduced-motion:reduce){.tour-panel{animation:none!important}}
    @keyframes ticker-slide{from{transform:translateX(0)}to{transform:translateX(-50%)}}
    @keyframes ambient-shift{from{background-position:0% 45%}to{background-position:100% 55%}}
    @keyframes soft-pulse{0%,100%{box-shadow:0 0 0 3px #f2b47e20}50%{box-shadow:0 0 0 7px #f2b47e12}}
    @keyframes gentle-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}
    @media(prefers-reduced-motion:reduce){.hero-shell,.live-dot,.orbit-core,.ticker-track{animation:none!important}.motion-banner:hover .ticker-track{animation:none!important}}
    @media(max-width:900px){.hero-shell{grid-template-columns:1fr;padding:24px}.hero-side{display:none}.hero-title{font-size:31px}.page-title{font-size:2rem!important}}
    @media (max-width: 900px) {
      .block-container { padding-left:1rem;padding-right:1rem; }
      .paper-meta { grid-template-columns:repeat(2,minmax(0,1fr)); }
      h1 { font-size:1.8rem !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_state() -> None:
    st.session_state.setdefault("records", {})
    st.session_state.setdefault("active_id", None)
    st.session_state.setdefault("upload_widget_version", 0)
    st.session_state.setdefault("nav_page", "Übersicht")
    st.session_state.setdefault("guided_tour", False)
    if PORTFOLIO_DEMO_MODE:
        # If demo mode is enabled during a running session, remove any earlier
        # non-demo uploads from that session before rendering the app.
        records = st.session_state["records"]
        for record_id, record in list(records.items()):
            if not record.is_demo:
                del records[record_id]
        if st.session_state.active_id not in records:
            st.session_state.active_id = None
    if not os.getenv("KOSIT_VALIDATOR_URL"):
        try:
            configured_url = st.secrets.get("KOSIT_VALIDATOR_URL", "")
            if configured_url:
                os.environ["KOSIT_VALIDATOR_URL"] = str(configured_url)
        except Exception:
            pass


def _e(value: object | None, fallback: str = "–") -> str:
    return html.escape(str(value if value not in (None, "") else fallback))


def _money(value: Decimal | None, currency: str | None) -> str:
    if value is None:
        return "–"
    amount = f"{value:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{amount} {currency or ''}".strip()


def _avatar(name: str | None) -> str:
    words = [word for word in (name or "RK").replace("&", " ").split() if word]
    initials = "".join(word[0] for word in words[:2]).upper() or "RK"
    return html.escape(initials[:2])


def _status_badge(state: str) -> str:
    class_name, label = STATE_META.get(state, STATE_META["Neu"])
    return f"<span class='badge badge-{class_name}'><span class='badge-dot'></span>{html.escape(label)}</span>"


def _process_upload(filename: str, payload: bytes, *, demo: bool = False) -> tuple[str | None, str | None]:
    suffix = os.path.splitext(filename)[1].lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return None, f"{filename}: Bitte eine XML- oder PDF-Datei auswählen."
    if len(payload) > MAX_UPLOAD_MB * 1024 * 1024:
        return None, f"{filename}: Die Datei ist größer als {MAX_UPLOAD_MB} MB."
    digest = hashlib.sha256(payload).hexdigest()
    records: dict[str, InvoiceRecord] = st.session_state.records
    if digest in records:
        st.session_state.active_id = digest
        return digest, None
    try:
        parsed = parse_invoice_file(filename, payload)
    except InvoiceParseError as exc:
        return None, f"{filename}: {exc}"

    record = InvoiceRecord(
        record_id=digest,
        filename=filename,
        original_bytes=payload,
        invoice=parsed.invoice,
        invoice_xml=parsed.invoice_xml,
        source_format=parsed.source_format,
        created_at=datetime.now().astimezone(),
        review_state="Neu",
        review_note="",
        is_demo=demo,
        pdf_text=parsed.pdf_text,
    )
    record.findings = run_validation(record).findings
    records[digest] = record
    st.session_state.active_id = digest
    return digest, None


def _sample_xml(kind: str) -> bytes:
    seller = """<cac:AccountingSupplierParty><cac:Party>
      <cac:PartyName><cbc:Name>Nordlicht Elektrotechnik GmbH</cbc:Name></cac:PartyName>
      <cac:PartyTaxScheme><cbc:CompanyID>DE123456789</cbc:CompanyID><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>
    </cac:Party></cac:AccountingSupplierParty>"""
    if kind == "review":
        seller = "<cac:AccountingSupplierParty><cac:Party/></cac:AccountingSupplierParty>"
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:CustomizationID>urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0</cbc:CustomizationID>
  <cbc:ProfileID>urn:fdc:peppol.eu:2017:poacc:billing:01:1.0</cbc:ProfileID>
  <cbc:ID>NL-2026-1001</cbc:ID><cbc:IssueDate>2026-10-02</cbc:IssueDate><cbc:DueDate>2026-11-01</cbc:DueDate>
  <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode><cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
  {seller}
  <cac:AccountingCustomerParty><cac:Party><cac:PartyName><cbc:Name>Werkstatt am Park GmbH</cbc:Name></cac:PartyName>
    <cac:PartyTaxScheme><cbc:CompanyID>DE987654321</cbc:CompanyID><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>
  </cac:Party></cac:AccountingCustomerParty>
  <cac:PaymentMeans><cbc:PaymentMeansCode>58</cbc:PaymentMeansCode><cac:PayeeFinancialAccount><cbc:ID>DE89370400440532013000</cbc:ID></cac:PayeeFinancialAccount></cac:PaymentMeans>
  <cac:TaxTotal><cbc:TaxAmount currencyID="EUR">190.00</cbc:TaxAmount><cac:TaxSubtotal>
    <cbc:TaxableAmount currencyID="EUR">1000.00</cbc:TaxableAmount><cbc:TaxAmount currencyID="EUR">190.00</cbc:TaxAmount>
    <cac:TaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>19</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:TaxCategory>
  </cac:TaxSubtotal></cac:TaxTotal>
  <cac:LegalMonetaryTotal><cbc:LineExtensionAmount currencyID="EUR">1000.00</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="EUR">1000.00</cbc:TaxExclusiveAmount><cbc:TaxInclusiveAmount currencyID="EUR">1190.00</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="EUR">1190.00</cbc:PayableAmount></cac:LegalMonetaryTotal>
  <cac:InvoiceLine><cbc:ID>1</cbc:ID><cbc:InvoicedQuantity unitCode="C62">10</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="EUR">1000.00</cbc:LineExtensionAmount><cac:Item><cbc:Name>LED-Arbeitsleuchten, Typ L-40</cbc:Name>
      <cac:ClassifiedTaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>19</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:ClassifiedTaxCategory>
    </cac:Item><cac:Price><cbc:PriceAmount currencyID="EUR">100.00</cbc:PriceAmount></cac:Price></cac:InvoiceLine>
</Invoice>'''
    return xml.encode("utf-8")


def _demo_xml(spec: dict[str, str]) -> bytes:
    net = Decimal(spec["net"])
    tax = (net * Decimal("0.19")).quantize(Decimal("0.01"))
    gross = net + tax
    vat = f"<cac:PartyTaxScheme><cbc:CompanyID>{spec['vat']}</cbc:CompanyID><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>" if spec.get("vat") else ""
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
<cbc:CustomizationID>urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0</cbc:CustomizationID>
<cbc:ID>{spec["number"]}</cbc:ID><cbc:IssueDate>{spec["date"]}</cbc:IssueDate><cbc:DueDate>{spec["due"]}</cbc:DueDate><cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode><cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
<cac:AccountingSupplierParty><cac:Party><cac:PartyName><cbc:Name>{spec["supplier"]}</cbc:Name></cac:PartyName>{vat}</cac:Party></cac:AccountingSupplierParty>
<cac:AccountingCustomerParty><cac:Party><cac:PartyName><cbc:Name>Werkstatt am Park GmbH</cbc:Name></cac:PartyName></cac:Party></cac:AccountingCustomerParty>
<cac:PaymentMeans><cbc:PaymentMeansCode>58</cbc:PaymentMeansCode><cac:PayeeFinancialAccount><cbc:ID>DE89370400440532013000</cbc:ID></cac:PayeeFinancialAccount></cac:PaymentMeans>
<cac:TaxTotal><cbc:TaxAmount currencyID="EUR">{tax:.2f}</cbc:TaxAmount><cac:TaxSubtotal><cbc:TaxableAmount currencyID="EUR">{net:.2f}</cbc:TaxableAmount><cbc:TaxAmount currencyID="EUR">{tax:.2f}</cbc:TaxAmount><cac:TaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>19</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:TaxCategory></cac:TaxSubtotal></cac:TaxTotal>
<cac:LegalMonetaryTotal><cbc:LineExtensionAmount currencyID="EUR">{net:.2f}</cbc:LineExtensionAmount><cbc:TaxExclusiveAmount currencyID="EUR">{net:.2f}</cbc:TaxExclusiveAmount><cbc:TaxInclusiveAmount currencyID="EUR">{gross:.2f}</cbc:TaxInclusiveAmount><cbc:PayableAmount currencyID="EUR">{gross:.2f}</cbc:PayableAmount></cac:LegalMonetaryTotal>
<cac:InvoiceLine><cbc:ID>1</cbc:ID><cbc:InvoicedQuantity unitCode="C62">1</cbc:InvoicedQuantity><cbc:LineExtensionAmount currencyID="EUR">{net:.2f}</cbc:LineExtensionAmount><cac:Item><cbc:Name>{spec["item"]}</cbc:Name></cac:Item><cac:Price><cbc:PriceAmount currencyID="EUR">{net:.2f}</cbc:PriceAmount></cac:Price></cac:InvoiceLine></Invoice>'''
    return xml.encode("utf-8")


def _load_demo_workspace() -> None:
    samples = [
        {"supplier":"Nordlicht Elektrotechnik GmbH","number":"NL-2026-1001","date":"2026-10-02","due":"2026-11-01","net":"1000.00","vat":"DE123456789","item":"LED-Arbeitsleuchten","state":"In Prüfung"},
        {"supplier":"Bergmann Bürobedarf GmbH","number":"BB-2026-084","date":"2026-10-04","due":"2026-10-18","net":"286.40","vat":"DE244781930","item":"Büromaterial","state":"Freigegeben"},
        {"supplier":"Hanseatic Cloud GmbH","number":"","date":"2026-10-06","due":"2026-10-13","net":"84.00","vat":"","item":"Cloud-Arbeitsplatz, Oktober","state":"Rückfrage nötig"},
        {"supplier":"Kranich Energie GmbH","number":"KE-2026-510","date":"2026-10-07","due":"2026-11-06","net":"1240.00","vat":"DE317620084","item":"Strom und Netznutzung","state":"Neu"},
        {"supplier":"RheinWerk Logistik GmbH","number":"RW-2026-222","date":"2026-10-08","due":"2026-10-28","net":"680.00","vat":"DE219700456","item":"Warentransport","state":"Freigegeben"},
        {"supplier":"Nordlicht Elektrotechnik GmbH","number":"NL-2026-1001","date":"2026-10-08","due":"2026-11-07","net":"160.00","vat":"DE123456789","item":"Montagematerial","state":"Neu"},
    ]
    for i, sample in enumerate(samples):
        filename = f"demo-{i + 1}-{sample['supplier'].split()[0].lower()}.xml"
        record_id, _ = _process_upload(filename, _demo_xml(sample), demo=True)
        if record_id:
            record = st.session_state.records[record_id]
            record.review_state = sample["state"]
            if sample["state"] == "Rückfrage nötig":
                record.review_note = "Rechnungsnummer bitte beim Lieferanten nachfragen"
    for record in st.session_state.records.values():
        if record.is_demo and record.invoice.seller_name == "Hanseatic Cloud GmbH":
            st.session_state.active_id = record.record_id
            break


def _duplicate_of(record: InvoiceRecord) -> str | None:
    invoice = record.invoice
    if not invoice.invoice_number or not invoice.seller_name:
        return None
    candidate = (invoice.seller_name.casefold().strip(), invoice.invoice_number.casefold().strip())
    for other in st.session_state.records.values():
        if other.record_id == record.record_id:
            continue
        other_key = ((other.invoice.seller_name or "").casefold().strip(), (other.invoice.invoice_number or "").casefold().strip())
        if candidate == other_key:
            return other.filename
    return None


def _stats(records: list[InvoiceRecord]) -> tuple[int, int, int, Decimal]:
    open_count = sum(record.review_state not in {"Freigegeben", "Abgelehnt"} for record in records)
    attention = sum(any(item.severity == "error" for item in record.findings) for record in records)
    approved = sum(record.review_state == "Freigegeben" for record in records)
    total_eur = sum(
        (record.invoice.payable_amount or Decimal("0") for record in records if (record.invoice.currency or "").upper() == "EUR"),
        Decimal("0"),
    )
    return open_count, attention, approved, total_eur


def _due_soon_records(records: list[InvoiceRecord]) -> list[InvoiceRecord]:
    """Return open invoices already due or due within the next seven days."""
    today = datetime.now().astimezone().date()
    cutoff = today + timedelta(days=7)
    due_records: list[tuple[datetime, InvoiceRecord]] = []
    for record in records:
        if record.review_state in {"Freigegeben", "Abgelehnt"} or not record.invoice.due_date:
            continue
        try:
            due = datetime.fromisoformat(record.invoice.due_date[:10])
        except ValueError:
            continue
        if due.date() <= cutoff:
            due_records.append((due, record))
    return [record for _, record in sorted(due_records, key=lambda pair: pair[0])]


def _stat_card(label: str, value: str, detail: str, icon: str) -> str:
    return (
        "<div class='stat-card'>"
        f"<div class='stat-top'><span>{html.escape(label)}</span><span class='stat-icon'>{html.escape(icon)}</span></div>"
        f"<div class='stat-value'>{html.escape(value)}</div><div class='stat-note'>{html.escape(detail)}</div>"
        "</div>"
    )


def _render_check(finding: Finding) -> None:
    severity = finding.severity if finding.severity in {"error", "warning", "info"} else "info"
    icon = {"error": "!", "warning": "↗", "info": "✓"}[severity]
    st.markdown(
        f"<div class='check-row'><div class='check-icon {severity}'>{icon}</div>"
        f"<div><div class='check-title'>{_e(finding.title)}</div><div class='check-copy'>{_e(finding.message)}</div></div></div>",
        unsafe_allow_html=True,
    )


def _set_navigation_destination(page: str) -> None:
    """Defer radio navigation until the next run, before its widget is created."""
    st.session_state["navigation_destination"] = page


def _open_invoice(record_id: str) -> None:
    st.session_state.active_id = record_id
    _set_navigation_destination("Eingang & Prüfung")


def _load_demo_and_open_overview() -> None:
    _load_demo_workspace()
    st.session_state["toast_notice"] = "Der fiktive Demo-Arbeitsplatz ist bereit."
    _set_navigation_destination("Übersicht")


TOUR_STEPS = [
    ("Übersicht", "Dein Arbeitscockpit", "Hier siehst du offene Vorgänge, Prüfhilfen und das erkannte Rechnungsvolumen."),
    ("Eingang & Prüfung", "Beleg sicher ausprobieren", "Öffentliche Demo: Uploads sind absichtlich gesperrt. Lade hier einen der fiktiven Beispieldatensätze."),
    ("Prüfzentrum", "Prüfumfang verstehen", "Sieh dir an, welche lokalen Hinweise aktiv sind und wann ein externer KoSIT-Validator verbunden wäre."),
    ("Lieferanten", "Muster erkennen", "Die Lieferantenansicht gruppiert fiktive Belege und zeigt Summen sowie offene Prüfhilfen."),
]


def _finish_guided_tour() -> None:
    st.session_state["guided_tour"] = False


def _add_demo_example(kind: str, filename: str) -> None:
    _, error = _process_upload(filename, _sample_xml(kind), demo=True)
    if error:
        st.error(error)
        return
    st.session_state["toast_notice"] = "Fiktiver Beispieldatensatz wurde zum Demo-Arbeitsplatz hinzugefügt."


def _render_portfolio_banner() -> None:
    if PORTFOLIO_DEMO_MODE:
        st.markdown(
            "<div class='demo-mode-banner'><div class='demo-mode-icon'>i</div><div class='demo-mode-copy'>"
            "<strong>Öffentliche Portfolio-Demo</strong><br><span>Es werden nur fiktive Belege verwendet. Der Upload echter Dokumente ist deaktiviert.</span>"
            "</div></div>",
            unsafe_allow_html=True,
        )


def _render_tour_annotation(page: str) -> None:
    if not st.session_state.get("guided_tour"):
        return
    pages = [step[0] for step in TOUR_STEPS]
    if page not in pages:
        return
    index = pages.index(page)
    title, copy = TOUR_STEPS[index][1:]
    st.markdown(
        f"<div class='tour-panel'><div class='tour-kicker'>Geführte Produkttour · Schritt {index + 1} von {len(TOUR_STEPS)}</div>"
        f"<strong>{_e(title)}</strong><p>{_e(copy)}</p></div>",
        unsafe_allow_html=True,
    )
    st.progress((index + 1) / len(TOUR_STEPS), text=f"{index + 1} / {len(TOUR_STEPS)} Schritte")
    if index < len(TOUR_STEPS) - 1:
        next_page = TOUR_STEPS[index + 1][0]
        st.button(
            f"Weiter: {next_page} →",
            key=f"tour_next_{index}",
            on_click=_set_navigation_destination,
            args=(next_page,),
        )
    else:
        st.button("Tour abschließen ✓", key="tour_finish", on_click=_finish_guided_tour)


def _render_sidebar(records: list[InvoiceRecord]) -> str:
    connected = bool(os.getenv("KOSIT_VALIDATOR_URL", "").strip())
    opened = sum(r.review_state not in {"Freigegeben", "Abgelehnt"} for r in records)
    pages = ["Übersicht", "Eingang & Prüfung", "Lieferanten", "Prüfzentrum", "Datenschutz & Setup"]
    st.sidebar.markdown("<div class='brand'><div class='brand-icon'>R</div><div><div class='brand-name'>Rechnungsklar</div><div class='brand-caption'>E-invoice workspace</div></div></div>", unsafe_allow_html=True)
    st.sidebar.markdown("<div class='nav-label'>ARBEITSBEREICH</div>", unsafe_allow_html=True)
    destination = st.session_state.pop("navigation_destination", None)
    if destination in pages:
        st.session_state.nav_page = destination
    st.sidebar.radio("Navigation", pages, key="nav_page", label_visibility="collapsed")
    st.sidebar.markdown("<div class='sidebar-panel'><div class='sidebar-panel-title'>HEUTE IM EINGANG</div>"
        f"<div class='sidebar-panel-value'>{opened:02d} offene Vorgänge</div>"
        f"<div class='sidebar-panel-copy'>{'KoSIT verbunden.' if connected else 'Lokale Vorprüfung · KoSIT nicht verbunden.'}</div></div>", unsafe_allow_html=True)
    st.sidebar.markdown("<div class='nav-label' style='margin-top:19px'>DEMO & EINSTIEG</div>", unsafe_allow_html=True)
    st.sidebar.caption("Fiktive Daten zeigen den kompletten Ablauf.")
    st.sidebar.button("Demo-Arbeitsplatz laden", use_container_width=True, type="primary", key="load_demo_workspace", on_click=_load_demo_and_open_overview)
    st.sidebar.checkbox("Geführte Produkttour", key="guided_tour", help="Zeigt kurze, passende Hinweise während du die Demo erkundest.")
    st.sidebar.markdown("<div class='sidebar-footnote'>Demo-Modus · Belege bleiben im Arbeitsspeicher dieser Sitzung. Keine echten Rechnungen in eine öffentliche Demo laden.</div>", unsafe_allow_html=True)
    return st.session_state.nav_page


def _render_queue(records: list[InvoiceRecord]) -> None:
    title_col, count_col = st.columns([2, 1])
    with title_col:
        st.markdown("### Rechnungseingang")
    with count_col:
        st.markdown(f"<div style='text-align:right;color:#859188;font-size:11px;padding-top:8px'>{len(records)} Dokumente</div>", unsafe_allow_html=True)
    filter_value = st.radio("Ansicht", ["Alle", "Offen", "Fällig & überfällig", "Freigegeben"], horizontal=True, label_visibility="collapsed", key="queue_filter")
    if filter_value == "Offen":
        shown = [record for record in records if record.review_state not in {"Freigegeben", "Abgelehnt"}]
    elif filter_value == "Fällig & überfällig":
        shown = _due_soon_records(records)
    elif filter_value == "Freigegeben":
        shown = [record for record in records if record.review_state == "Freigegeben"]
    else:
        shown = records
    query = st.text_input("Rechnungen suchen", placeholder="Lieferant, Nummer oder Datei", label_visibility="collapsed", key="queue_search")
    if query.strip():
        needle = query.casefold().strip()
        shown = [record for record in shown if needle in (record.invoice.seller_name or "").casefold()
                 or needle in (record.invoice.invoice_number or "").casefold()
                 or needle in record.filename.casefold()]
    if not shown:
        st.caption("Keine Rechnungen in diesem Filter.")
        return

    for index, record in enumerate(sorted(shown, key=lambda item: item.created_at, reverse=True)):
        invoice = record.invoice
        active = record.record_id == st.session_state.active_id
        with st.container(border=True):
            avatar_col, main_col, amount_col = st.columns([.18, .58, .24], vertical_alignment="center")
            with avatar_col:
                st.markdown(f"<div class='avatar a{index % 4}'>{_avatar(invoice.seller_name)}</div>", unsafe_allow_html=True)
            with main_col:
                st.markdown(f"<div class='queue-name'>{_e(invoice.seller_name, 'Lieferant nicht erkannt')}</div><div class='queue-id'>{_e(invoice.invoice_number, record.filename)}</div>", unsafe_allow_html=True)
            with amount_col:
                st.markdown(f"<div class='queue-amount'>{_e(_money(invoice.payable_amount, invoice.currency))}</div><div class='queue-date'>{_e(invoice.issue_date, 'Ohne Datum')}</div>", unsafe_allow_html=True)
            meta_col, action_col = st.columns([1, .36], vertical_alignment="center")
            with meta_col:
                st.markdown(_status_badge(record.review_state), unsafe_allow_html=True)
            with action_col:
                label = "Geöffnet ✓" if active else "Ansehen →"
                if st.button(label, key=f"open_{record.record_id}", use_container_width=True, type="primary" if active else "secondary"):
                    st.session_state.active_id = record.record_id
                    st.rerun()


def _paper_markup(record: InvoiceRecord) -> str:
    invoice = record.invoice
    line_markup = ""
    for line in invoice.lines[:8]:
        amount = _money(line.net_amount, invoice.currency)
        quantity = f"Menge {line.quantity}" if line.quantity else "Rechnungsposition"
        line_markup += (
            "<div class='line-row'><div><div class='line-desc'>"
            f"{_e(line.description, 'Position ohne Bezeichnung')}</div><div class='line-detail'>{_e(quantity)}</div></div>"
            f"<div class='line-amount'>{_e(amount)}</div></div>"
        )
    if not line_markup:
        line_markup = "<div class='line-row'><div><div class='line-desc'>Keine Positionen ausgelesen</div><div class='line-detail'>Bitte Original prüfen</div></div></div>"
    due_label = "Zahlungsziel" if invoice.due_date else "Zahlungsziel"
    net = _money(invoice.net_amount, invoice.currency)
    tax = _money(invoice.tax_amount, invoice.currency)
    gross = _money(invoice.payable_amount, invoice.currency)
    return (
        "<div class='invoice-paper'><div class='paper-top'><span class='paper-logo'>Rechnungsbeleg · strukturierte Daten</span>"
        f"<span class='paper-ref'>{_e(invoice.syntax)} · {_e(invoice.currency)}</span></div>"
        f"<div class='paper-seller'>{_e(invoice.seller_name, 'Lieferant nicht erkannt')}</div>"
        f"<div class='paper-sub'>Rechnung an {_e(invoice.buyer_name, 'Empfänger nicht erkannt')}</div>"
        "<div class='paper-meta'>"
        f"<div><div class='paper-label'>Rechnungsnummer</div><div class='paper-value'>{_e(invoice.invoice_number)}</div></div>"
        f"<div><div class='paper-label'>Rechnungsdatum</div><div class='paper-value'>{_e(invoice.issue_date, 'Nicht angegeben')}</div></div>"
        f"<div><div class='paper-label'>{due_label}</div><div class='paper-value'>{_e(invoice.due_date, 'Nicht angegeben')}</div></div>"
        f"<div><div class='paper-label'>USt-IdNr. Lieferant</div><div class='paper-value'>{_e(invoice.seller_vat_id)}</div></div>"
        f"<div><div class='paper-label'>Zahlungskonto</div><div class='paper-value'>{_e(invoice.iban, 'Nicht angegeben')}</div></div>"
        f"<div><div class='paper-label'>Format</div><div class='paper-value'>{_e(record.source_format)}</div></div>"
        "</div><div class='line-heading'><span>Leistungsbeschreibung</span><span>Nettobetrag</span></div>"
        f"{line_markup}<div class='paper-totals'>"
        f"<div class='total-row'><span>Nettosumme</span><strong>{_e(net)}</strong></div>"
        f"<div class='total-row'><span>Steuern</span><strong>{_e(tax)}</strong></div>"
        f"<div class='total-due'><span>Zahlbetrag</span><span>{_e(gross)}</span></div>"
        "</div></div>"
    )


def _render_checks(record: InvoiceRecord) -> None:
    st.markdown("### Prüfstatus")
    if record.validation_source == "KoSIT":
        status_icon = "✓" if record.kosit_status and "akzeptiert" in record.kosit_status else "!"
        st.markdown(f"<div class='sidebar-panel'><div class='sidebar-panel-title'>KoSIT · technischer Prüfbericht</div><div class='sidebar-panel-value'>{status_icon} {_e(record.kosit_status, 'Ergebnis erhalten')}</div><div class='sidebar-panel-copy'>Ergebnis der verbundenen Prüfkonfiguration.</div></div>", unsafe_allow_html=True)
        with st.expander("Prüfbericht aufklappen"):
            if record.kosit_report:
                st.code(record.kosit_report[:20000], language="xml")
            else:
                st.caption("Kein Berichttext vom Dienst erhalten.")
    else:
        st.markdown("<div class='sidebar-panel'><div class='sidebar-panel-title'>Lokale Vorprüfung</div><div class='sidebar-panel-value'>Kein offizieller Validator verbunden</div><div class='sidebar-panel-copy'>Diese Hinweise zeigen nur, ob wichtige Werte ausgelesen wurden. Sie sind keine EN 16931- oder Steuerbescheinigung.</div></div>", unsafe_allow_html=True)
        if os.getenv("KOSIT_VALIDATOR_URL", "").strip():
            if st.button("Mit KoSIT prüfen", type="primary", use_container_width=True, key=f"kosit_{record.record_id}"):
                with st.spinner("XML wird an den konfigurierten KoSIT-Dienst gesendet …"):
                    result = run_validation(record, force_kosit=True)
                    record.findings = result.findings
                    record.validation_source = result.source
                    record.kosit_status = result.kosit_status
                    record.kosit_report = result.kosit_report
                    record.kosit_error = result.kosit_error
                st.rerun()
            if record.kosit_error:
                st.warning(record.kosit_error)
        else:
            st.caption("KoSIT-Verbindung kannst du später in der Projektkonfiguration ergänzen.")

    if not record.findings:
        st.markdown("<div class='check-row'><div class='check-icon info'>✓</div><div><div class='check-title'>Keine lokalen Hinweise</div><div class='check-copy'>Für diese Rechnung liegen keine Extraktionshinweise vor.</div></div></div>", unsafe_allow_html=True)
    else:
        for finding in record.findings[:5]:
            _render_check(finding)
        if len(record.findings) > 5:
            st.caption(f"+ {len(record.findings) - 5} weitere Hinweise")

    if record.pdf_text:
        st.markdown("### PDF / XML")
        st.caption("Automatische Lesehilfe · mögliche Konflikte visuell bestätigen")
        hints = pdf_review_hints(record)
        if hints:
            for item in hints:
                needs_review = item["Status"] == "Prüfen"
                icon_class = "warning" if needs_review else "info"
                icon = "!" if needs_review else "✓"
                st.markdown(
                    f"<div class='check-row'><div class='check-icon {icon_class}'>{icon}</div>"
                    f"<div><div class='check-title'>{_e(item['Feld'])} · {_e(item['Status'])}</div>"
                    f"<div class='check-copy'>{_e(item['Hinweis'])}</div></div></div>",
                    unsafe_allow_html=True,
                )
        st.caption("Bei einer ZUGFeRD-Abweichung ist der strukturierte XML-Teil maßgeblich. Text-Extraktion kann Werte übersehen.")


def _render_review_actions(record: InvoiceRecord) -> None:
    st.markdown("### Nächster Schritt")
    with st.form(f"review_form_{record.record_id}"):
        chosen_state = st.selectbox("Bearbeitungsstatus", STATES, index=STATES.index(record.review_state), key=f"state_{record.record_id}")
        note = st.text_input("Notiz für dein Team", value=record.review_note, placeholder="z. B. Projektzuordnung bestätigen", key=f"note_{record.record_id}")
        if st.form_submit_button("Änderung übernehmen", type="primary", use_container_width=True):
            record.review_state = chosen_state
            record.review_note = note.strip()
            st.rerun()


def _render_selected(record: InvoiceRecord) -> None:
    invoice = record.invoice
    duplicate = _duplicate_of(record)
    with st.container(border=True):
        top_left, top_right = st.columns([1.5, .75], vertical_alignment="center")
        with top_left:
            st.markdown("<div class='eyebrow'>Rechnungsdetails</div>", unsafe_allow_html=True)
            st.markdown(f"## {_e(invoice.seller_name, 'Lieferant nicht erkannt')}")
            st.caption(f"{invoice.invoice_number or record.filename}  ·  Eingang am {record.created_at.strftime('%d.%m.%Y um %H:%M')}")
        with top_right:
            st.markdown(_status_badge(record.review_state), unsafe_allow_html=True)
            if invoice.payable_amount is not None:
                st.markdown(f"<div style='text-align:right;font-size:25px;font-weight:800;letter-spacing:-.055em;color:#173f31;margin-top:8px'>{_e(_money(invoice.payable_amount, invoice.currency))}</div>", unsafe_allow_html=True)

        if record.is_demo:
            st.info("Fiktive Beispieldaten", icon="✳️")
        if duplicate:
            st.warning(f"Mögliche Dublette: gleiche Lieferanten- und Rechnungsnummer wie in {duplicate}.", icon="⚠️")

        st.markdown(
            "<div class='progress-track'><div class='progress-step active'><span class='progress-num'>1</span>Datei eingelesen</div>"
            "<div class='progress-line'></div><div class='progress-step active'><span class='progress-num'>2</span>Daten geprüft</div>"
            "<div class='progress-line'></div><div class='progress-step'><span class='progress-num'>3</span>Freigabe</div></div>",
            unsafe_allow_html=True,
        )

        preview_col, action_col = st.columns([1.6, .9], gap="large")
        with preview_col:
            st.markdown(_paper_markup(record), unsafe_allow_html=True)
            line_count = len(invoice.lines)
            label = "Position" if line_count == 1 else "Positionen"
            st.markdown(f"<div class='upload-caption' style='padding:9px 4px 0'>Vorschau aus dem strukturierten XML · {line_count} {label} · Original bleibt unverändert</div>", unsafe_allow_html=True)
        with action_col:
            _render_checks(record)

        st.divider()
        left, right = st.columns([1.45, 1], gap="large")
        with left:
            _render_review_actions(record)
        with right:
            st.markdown("### Beleg sichern")
            st.caption("Original und Prüfungshinweise gemeinsam weitergeben.")
            st.download_button(
                "↓  Originaldatei herunterladen",
                data=record.original_bytes,
                file_name=record.filename,
                mime="application/pdf" if record.filename.lower().endswith(".pdf") else "application/xml",
                use_container_width=True,
                key=f"download_original_{record.record_id}",
            )
            st.download_button(
                "↓  Prüfpaket als ZIP",
                data=build_review_bundle(record),
                file_name=f"rechnungsklar-{record.record_id[:10]}.zip",
                mime="application/zip",
                use_container_width=True,
                key=f"download_bundle_{record.record_id}",
            )

        with st.expander("Technische Quelldaten anzeigen"):
            st.caption("Rohdaten der strukturierten Rechnungsdatei")
            st.code(record.invoice_xml.decode("utf-8", errors="replace")[:30000], language="xml")
            if record.pdf_text:
                st.caption("Extrahierter PDF-Text · nur Lesehilfe")
                st.code(record.pdf_text[:10000])


def _render_empty_state(*, show_samples: bool = True) -> None:
    empty_title = "Dein Demo-Eingang wartet." if PORTFOLIO_DEMO_MODE else "Dein Eingang ist bereit."
    empty_copy = (
        "Wähle oben einen fiktiven Beispieldatensatz. Lieferant, erkannte Felder und Prüfhilfen erscheinen danach in der Belegansicht."
        if PORTFOLIO_DEMO_MODE else
        "Lade deine erste strukturierte Rechnung hoch oder öffne ein Beispieldokument. Lieferanten, Beträge und Positionen erscheinen danach in einer lesbaren Belegansicht."
    )
    st.markdown(
        f"<div class='empty-state'><div class='empty-icon'>↥</div><div class='empty-title'>{_e(empty_title)}</div>"
        f"<div class='empty-copy'>{_e(empty_copy)}</div></div>",
        unsafe_allow_html=True,
    )
    if not show_samples:
        return
    st.write("")
    sample_col1, sample_col2, _ = st.columns([1, 1, 2])
    with sample_col1:
        st.button("Beispiel öffnen", type="primary", use_container_width=True, key="empty_sample_valid",
                  on_click=_add_demo_example, args=("valid", "nordlicht-rechnung-1001.xml"))
    with sample_col2:
        st.button("Prüffall ansehen", use_container_width=True, key="empty_sample_review",
                  on_click=_add_demo_example, args=("review", "lieferant-pruefung-1002.xml"))


def _page_header(kicker: str, title: str, copy: str) -> None:
    st.markdown(f"<div class='eyebrow'>{_e(kicker)}</div><h1 class='page-title'>{_e(title)}</h1><div class='page-subtitle'>{_e(copy)}</div>", unsafe_allow_html=True)


def _render_overview(records: list[InvoiceRecord]) -> None:
    opened, attention, approved, total = _stats(records)
    due_records = _due_soon_records(records)
    st.markdown("<div class='hero-shell'><div><div class='hero-kicker'><span class='live-dot'></span> DEIN DIGITALER RECHNUNGSEINGANG</div><div class='hero-title'>Klarheit in jedem<br>Rechnungsformat.</div>"
        "<div class='hero-copy'>Strukturierte E-Rechnungen lesen, Auffälligkeiten erkennen und den nächsten Schritt sauber dokumentieren.</div><div class='hero-tags'><span>XRechnung</span><span>ZUGFeRD</span><span>UBL · CII</span></div></div>"
        "<div class='hero-side'><div class='hero-date'>" + datetime.now().astimezone().strftime("%d.%m.%Y") + "</div><div class='hero-orbit'><div class='orbit-core'><strong>" + f"{opened:02d}" +
        "</strong><span>offen</span></div><div class='orbit-label label-one'>Eingang</div><div class='orbit-label label-two'>Prüfen</div><div class='orbit-label label-three'>Freigeben</div></div><div class='hero-side-caption'>Dein Arbeitsstand auf einen Blick</div></div></div>", unsafe_allow_html=True)
    a,b,c = st.columns([1,1,2.2], vertical_alignment="center")
    with a:
        st.button("＋ Beispieldokument testen", type="primary", use_container_width=True, key="overview_inbox",
                  on_click=_set_navigation_destination, args=("Eingang & Prüfung",))
    with b:
        st.button("Demo-Daten ansehen", use_container_width=True, key="overview_demo", on_click=_load_demo_and_open_overview)
    with c:
        st.markdown("<div class='privacy-inline'>⌑ &nbsp; Fiktive Demo-Belege · nur im Sitzungsspeicher</div>", unsafe_allow_html=True)
    ticker_items = (
        f"<span>{len(records):02d} BELEGE IM WORKSPACE</span><b>✦</b>"
        f"<span>{attention:02d} LOKALE PRÜFHINWEISE</span><b>✦</b>"
        "<span>XRECHNUNG · ZUGFERD · UBL · CII</span><b>✦</b>"
        "<span>IMPORTIEREN · PRÜFEN · WEITERGEBEN</span><b>✦</b>"
    )
    st.markdown(
        "<div class='motion-banner'><span class='ticker-label'>WORKSPACE LIVE</span><div class='ticker-window'><div class='ticker-track'>"
        + ticker_items + ticker_items + "</div></div></div>",
        unsafe_allow_html=True,
    )
    cards = st.columns(5)
    cards[0].markdown(_stat_card("Offen zur Bearbeitung", str(opened), "Im aktiven Workflow", "↗"), unsafe_allow_html=True)
    cards[1].markdown(_stat_card("Prüfhilfe erforderlich", str(attention), "Lokale Hinweise zur Sichtprüfung", "!"), unsafe_allow_html=True)
    cards[2].markdown(_stat_card("Fällig / überfällig", str(len(due_records)), "Jetzt oder innerhalb von 7 Tagen", "◷"), unsafe_allow_html=True)
    cards[3].markdown(_stat_card("Freigegeben", str(approved), "Im aktuellen Sitzungsbestand", "✓"), unsafe_allow_html=True)
    cards[4].markdown(_stat_card("Erkanntes Volumen", _money(total, "EUR") if records else "0,00 €", "Erkannte EUR-Belege", "€"), unsafe_allow_html=True)

    left,right = st.columns([1.35,1], gap="large")
    with left:
        st.markdown("<div class='dashboard-heading'><div><div class='eyebrow'>ARBEITSLISTE</div><h2>Was braucht Aufmerksamkeit?</h2></div><span class='subtle-count'>" + str(opened) + " offen</span></div>", unsafe_allow_html=True)
        pending = sorted([r for r in records if r.review_state not in {"Freigegeben","Abgelehnt"}], key=lambda r: (not any(f.severity=="error" for f in r.findings), r.created_at))[:4]
        if not pending:
            msg = "Dein Arbeitsbereich wartet auf Belege" if not records else "Alles im grünen Bereich"
            next_action = "Öffne ein Beispieldokument oder lade den Demo-Arbeitsplatz." if PORTFOLIO_DEMO_MODE else "Importiere eine Rechnung oder lade den Demo-Arbeitsplatz."
            st.markdown("<div class='calm-empty'><span>↥</span><div><strong>" + msg + "</strong><br>" + _e(next_action) + "</div></div>", unsafe_allow_html=True)
        for rec in pending:
            inv=rec.invoice
            urgent=any(f.severity=="error" for f in rec.findings) or rec.review_state=="Rückfrage nötig"
            st.markdown("<div class='focus-row'><div class='focus-icon " + ("tone-attention" if urgent else "tone-review") + "'>" + ("!" if urgent else "↗") + "</div><div class='focus-main'><div class='focus-name'>" +
                _e(inv.seller_name,"Lieferant nicht erkannt") + "</div><div class='focus-meta'>" + _e(inv.invoice_number,rec.filename) + " · " + _e(inv.issue_date,"Ohne Datum") +
                "</div></div><div class='focus-end'><div class='focus-amount'>" + _e(_money(inv.payable_amount,inv.currency)) + "</div><div class='focus-state'>" + _e(rec.review_state) + "</div></div></div>", unsafe_allow_html=True)
            _, button = st.columns([5,1])
            with button:
                st.button("Öffnen", key=f"focus_{rec.record_id}", use_container_width=True,
                          on_click=_open_invoice, args=(rec.record_id,))
    with right:
        st.markdown("<div class='dashboard-heading'><div><div class='eyebrow'>RECHNUNGSVOLUMEN</div><h2>Dein Bestand im Überblick</h2></div><span class='subtle-count'>Live aus Belegen</span></div>", unsafe_allow_html=True)
        breakdown = st.radio("Aufschlüsselung", ["Lieferanten", "Workflow-Status"], horizontal=True,
                             label_visibility="collapsed", key="spend_breakdown")
        amounts: dict[str,Decimal]={}
        for rec in records:
            if rec.invoice.payable_amount is not None and (rec.invoice.currency or "").upper()=="EUR":
                if breakdown == "Workflow-Status":
                    name = rec.review_state
                else:
                    name = rec.invoice.seller_name or "Nicht zugeordnet"
                amounts[name]=amounts.get(name,Decimal("0"))+rec.invoice.payable_amount
        ranking=sorted(amounts.items(),key=lambda pair:pair[1],reverse=True)[:5]
        if ranking:
            max_value=max(value for _,value in ranking) or Decimal("1")
            for name,value in ranking:
                width=max(4,int(float(value/max_value)*100))
                st.markdown("<div class='spend-row'><div class='spend-top'><span>" + _e(name) + "</span><strong>" + _e(_money(value,"EUR")) + "</strong></div><div class='spend-track'><div class='spend-fill' style='width:" + str(width) + "%'></div></div></div>",unsafe_allow_html=True)
        else:
            chart_copy = "Lade fiktive Beispieldaten, um erkannte Beträge zu sehen." if PORTFOLIO_DEMO_MODE else "Importiere Belege, um erkannte Beträge je Lieferant zu sehen."
            st.markdown("<div class='chart-empty'>" + _e(chart_copy) + "</div>",unsafe_allow_html=True)
        st.markdown("<div class='standard-note'><div class='standard-icon'>✓</div><div><strong>Für E-Rechnungen gemacht</strong><span>UBL- und CII-Daten werden lesbar, prüfbar und exportierbar aufbereitet.</span></div></div>",unsafe_allow_html=True)

    recent,flow=st.columns([1.35,1],gap="large")
    with recent:
        st.markdown("<div class='dashboard-heading'><div><div class='eyebrow'>LETZTE EINGÄNGE</div><h2>Zuletzt hinzugefügt</h2></div></div>",unsafe_allow_html=True)
        for rec in sorted(records,key=lambda r:r.created_at,reverse=True)[:4]:
            st.markdown("<div class='recent-row'><div class='recent-mark'></div><div class='recent-text'><strong>" + _e(rec.invoice.seller_name,"Lieferant nicht erkannt") +
                "</strong><span>" + _e(rec.invoice.invoice_number,rec.filename) + " · " + _e(rec.source_format) + "</span></div><div class='recent-amount'>" +
                _e(_money(rec.invoice.payable_amount,rec.invoice.currency)) + "</div></div>",unsafe_allow_html=True)
        if not records: st.caption("Deine Rechnungen erscheinen nach dem Import.")
    with flow:
        st.markdown("<div class='product-card'><div class='eyebrow'>RECHNUNGSKLAR WORKFLOW</div><div class='product-card-title'>Vom Dateieingang zur nachvollziehbaren Prüfung.</div><div class='workflow-mini'><div><i>01</i><span>Importieren</span></div><b></b><div><i>02</i><span>Einordnen</span></div><b></b><div><i>03</i><span>Weitergeben</span></div></div><p>Beleg, erkannte Felder, Prüfhilfen und Teamnotiz bleiben in einer Ansicht verbunden.</p></div>",unsafe_allow_html=True)


def _render_inbox(records: list[InvoiceRecord]) -> None:
    inbox_copy = "Fiktive Belege erfassen, Daten prüfen und den Demo-Workflow nachvollziehen." if PORTFOLIO_DEMO_MODE else "Belege erfassen, Daten prüfen und Entscheidungen nachvollziehbar festhalten."
    _page_header("EINGANG & PRÜFUNG","Deine Rechnungseingänge",inbox_copy)
    if PORTFOLIO_DEMO_MODE:
        with st.container(border=True):
            st.markdown("<div class='upload-head'><div><strong>Fiktive Belege ausprobieren</strong><span>Der Datei-Upload ist in dieser öffentlichen Portfolio-Demo deaktiviert.</span></div><div class='upload-mark'>✦</div></div>",unsafe_allow_html=True)
            st.caption("Wähle einen Beispieldatensatz. So kannst du den gesamten Prüfablauf ansehen, ohne echte Rechnungen hochzuladen.")
            sample_a, sample_b, _ = st.columns([1.15, 1.15, 1.7])
            with sample_a:
                st.button("✓ Saubere Beispielrechnung", type="primary", use_container_width=True,
                          key="inbox_sample_valid", on_click=_add_demo_example,
                          args=("valid", "nordlicht-rechnung-1001.xml"))
            with sample_b:
                st.button("! Prüffall mit Hinweisen", use_container_width=True,
                          key="inbox_sample_review", on_click=_add_demo_example,
                          args=("review", "lieferant-pruefung-1002.xml"))
    else:
        with st.container(border=True):
            st.markdown("<div class='upload-head'><div><strong>Rechnung hinzufügen</strong><span>XRechnung-XML oder ZUGFeRD-PDF · maximal 20 MB je Datei</span></div><div class='upload-mark'>↑</div></div>",unsafe_allow_html=True)
            uploads=st.file_uploader("Dateien hier ablegen oder auswählen",type=["xml","pdf"],accept_multiple_files=True,
                help=f"Ein normales PDF ohne eingebettetes Rechnungs-XML ist keine strukturierte E-Rechnung. Maximal {MAX_UPLOAD_MB} MB je Datei.",key=f"invoice_upload_{st.session_state.upload_widget_version}")
            if uploads:
                errors=[]
                for up in uploads:
                    _,error=_process_upload(up.name,up.getvalue())
                    if error: errors.append(error)
                if errors:
                    for error in errors: st.error(error)
                else:
                    st.session_state.upload_widget_version+=1
                    st.rerun()
    if not records:
        _render_empty_state(show_samples=not PORTFOLIO_DEMO_MODE)
        return
    opened,attention,approved,total=_stats(records)
    cols=st.columns(4)
    for col,label,value,note,icon in zip(cols,["Offen","Prüfhilfe","Freigegeben","Rechnungsvolumen"],[opened,attention,approved,_money(total,"EUR")],["Im Bearbeitungsprozess","Lokale Feldhinweise","Bereit zur Übergabe","Erkannte EUR-Beträge"],["↗","!","✓","€"]):
        col.markdown(_stat_card(label,str(value),note,icon),unsafe_allow_html=True)
    q,d=st.columns([.9,2.1],gap="large")
    with q:
        _render_queue(records)
        st.download_button("Posteingang exportieren · CSV",data=inbox_csv(records),file_name="rechnungsklar-posteingang.csv",mime="text/csv",use_container_width=True,key="download_inbox_csv")
    with d:
        active=st.session_state.records.get(st.session_state.active_id)
        if active: _render_selected(active)
        else: st.caption("Links eine Rechnung zum Prüfen auswählen.")


def _render_suppliers(records: list[InvoiceRecord]) -> None:
    _page_header("LIEFERANTEN","Beziehungen statt Tabellen.","Absender gruppiert nach echten Rechnungsdaten aus dieser Sitzung.")
    groups: dict[str,list[InvoiceRecord]]={}
    for rec in records: groups.setdefault((rec.invoice.seller_name or "Nicht erkannter Lieferant").strip(),[]).append(rec)
    query=st.text_input("Lieferanten filtern",placeholder="Name oder Rechnungsnummer suchen",key="supplier_search")
    matches=[(name,items) for name,items in groups.items() if query.casefold() in name.casefold() or any(query.casefold() in (r.invoice.invoice_number or "").casefold() for r in items)]
    if not matches:
        st.markdown("<div class='calm-empty'><span>⌕</span><div><strong>" + ("Keine Treffer" if groups else "Lieferanten erscheinen nach dem ersten Import") + "</strong><br>Die Übersicht entsteht aus eingegangenen Rechnungen.</div></div>",unsafe_allow_html=True)
        return
    columns=st.columns(2,gap="large")
    for i,(name,items) in enumerate(sorted(matches,key=lambda pair:len(pair[1]),reverse=True)):
        amount=sum((r.invoice.payable_amount or Decimal("0") for r in items if (r.invoice.currency or "").upper()=="EUR"),Decimal("0"))
        problems=sum(any(f.severity=="error" for f in r.findings) for r in items)
        latest=max(items,key=lambda r:r.created_at)
        with columns[i%2]:
            st.markdown("<div class='supplier-card'><div class='supplier-card-top'><div class='avatar'>" + _avatar(name) + "</div><div class='supplier-title-wrap'><strong>" + _e(name) +
                "</strong><span>" + str(len(items)) + " Beleg(e) · zuletzt " + _e(latest.invoice.issue_date,"ohne Datum") + "</span></div><div class='supplier-total'>" + _e(_money(amount,"EUR")) +
                "</div></div><div class='supplier-card-bottom'><span class='supplier-health " + ("needs-review" if problems else "looks-good") + "'>" + (f"{problems} mit Prüfhilfe" if problems else "Keine lokalen Hinweise") +
                "</span><span>" + _e(latest.invoice.invoice_number,latest.filename) + "</span></div></div>",unsafe_allow_html=True)
            st.button("Rechnungen öffnen →", key=f"supplier_{hashlib.sha1(name.encode()).hexdigest()[:8]}",
                      use_container_width=True, on_click=_open_invoice, args=(latest.record_id,))


def _render_compliance(records: list[InvoiceRecord]) -> None:
    _page_header("PRÜFZENTRUM","Was wurde wirklich geprüft?","Lokale Datenlesehilfe und technische Validierung werden klar getrennt.")
    connected=bool(os.getenv("KOSIT_VALIDATOR_URL","").strip())
    cols=st.columns(3)
    cols[0].markdown(_stat_card("XRechnung",str(sum("XRechnung" in r.source_format for r in records)),"Erkannte Rechnungsdateien","X"),unsafe_allow_html=True)
    cols[1].markdown(_stat_card("ZUGFeRD",str(sum("ZUGFeRD" in r.source_format for r in records)),"XML aus PDF gelesen","Z"),unsafe_allow_html=True)
    cols[2].markdown(_stat_card("KoSIT-Prüfungen",str(sum(r.validation_source=="KoSIT" for r in records)),"In dieser Sitzung","✓"),unsafe_allow_html=True)
    left,right=st.columns([1.15,.85],gap="large")
    with left:
        st.markdown("<div class='info-panel'><div class='eyebrow'>PRÜFUMFANG</div><h2>Derzeit in der App</h2><div class='compliance-step'><i>01</i><div><strong>XML sicher einlesen</strong><span>UBL- und CII-Daten sowie ZUGFeRD-Anhänge.</span></div><b>Aktiv</b></div><div class='compliance-step'><i>02</i><div><strong>Wichtige Werte extrahieren</strong><span>Lieferant, Rechnungsnummer, Datum und Beträge.</span></div><b>Aktiv</b></div><div class='compliance-step'><i>03</i><div><strong>Lokale Feldhinweise</strong><span>Markiert wichtige Werte, die nicht erkannt wurden.</span></div><b>Aktiv</b></div><div class='compliance-step'><i>04</i><div><strong>EN 16931-Regelprüfung</strong><span>Nur mit konfiguriertem KoSIT-Dienst verfügbar.</span></div><b class='step-optional'>" + ("Verbunden" if connected else "Optional") + "</b></div></div>",unsafe_allow_html=True)
    with right:
        st.markdown("<div class='info-panel'><div class='eyebrow'>TECHNISCHER VALIDATOR</div><h2>" + ("KoSIT konfiguriert" if connected else "KoSIT nicht verbunden") + "</h2><p>" +
            ("Die Aussagekraft hängt von Version und Szenario ab." if connected else "Die lokale Vorprüfung behauptet keine EN 16931-Konformität.") + "</p><div class='validator-state " + ("connected" if connected else "") +
            "'><span></span>" + ("Verbindungs-URL konfiguriert" if connected else "Nur lokale Vorprüfung aktiv") + "</div><div class='fineprint'>Ein technisches Prüfergebnis ist keine Steuerberatung und garantiert keine steuerliche Anerkennung.</div></div>",unsafe_allow_html=True)
        if not connected: st.caption("KOSIT_VALIDATOR_URL als Streamlit Secret konfigurieren; Details stehen in der README.")


def _render_setup(records: list[InvoiceRecord]) -> None:
    _page_header("DATENSCHUTZ & SETUP","Ein Prototyp mit klaren Grenzen.","Für echte Unternehmensdaten braucht es eine sichere Betriebsarchitektur.")
    left,right=st.columns([1.1,.9],gap="large")
    with left:
        st.markdown("<div class='info-panel'><div class='eyebrow'>SITZUNGSSTATUS</div><h2>Demo-Umgebung</h2><div class='setting-line'><span>Belege in dieser Sitzung</span><strong>" + str(len(records)) +
            "</strong></div><div class='setting-line'><span>Öffentlicher Datei-Upload</span><strong>Gesperrt</strong></div><div class='setting-line'><span>Speicherung</span><strong>Nur Sitzungsspeicher</strong></div><div class='setting-line'><span>Login / Nutzerrollen</span><strong>Nicht eingerichtet</strong></div><div class='setting-line'><span>GoBD-Archiv</span><strong>Nicht vorhanden</strong></div><div class='fineprint'>Es werden nur fiktive Beispiele verarbeitet. Die App führt kein dauerhaftes Archiv.</div></div>",unsafe_allow_html=True)
    with right:
        st.markdown("<div class='info-panel'><div class='eyebrow'>VOR PRODUKTIVNUTZUNG</div><h2>Produktreife aufbauen</h2><div class='roadmap-item'><i>01</i><div><strong>Mandantenfähige Anmeldung</strong><span>Getrennte Organisationen und Zugriffsrechte.</span></div></div><div class='roadmap-item'><i>02</i><div><strong>Verschlüsselte Ablage</strong><span>Aufbewahrung, Löschung, Backups, Audit-Trail.</span></div></div><div class='roadmap-item'><i>03</i><div><strong>Sichere Integrationen</strong><span>Validator, Steuerberatung, Buchhaltungssysteme.</span></div></div><div class='roadmap-item'><i>04</i><div><strong>Datenschutz & Betrieb</strong><span>Monitoring, AV-Verträge und Löschfristen.</span></div></div></div>",unsafe_allow_html=True)
    st.info("Demo-Schutz aktiv: Datei-Uploads sind gesperrt; alle Beispieldaten sind fiktiv.")


def main() -> None:
    _init_state()
    records: list[InvoiceRecord] = list(st.session_state.records.values())
    page=_render_sidebar(records)
    _render_portfolio_banner()
    notice = st.session_state.pop("toast_notice", None)
    if notice:
        st.toast(notice, icon="✅")
    _render_tour_annotation(page)
    if page=="Übersicht": _render_overview(records)
    elif page=="Eingang & Prüfung": _render_inbox(records)
    elif page=="Lieferanten": _render_suppliers(records)
    elif page=="Prüfzentrum": _render_compliance(records)
    else: _render_setup(records)
    st.markdown("<div class='app-footer'>RECHNUNGSKLAR <span>·</span> PORTFOLIO-PROTOTYP</div>",unsafe_allow_html=True)


if __name__ == "__main__":
    main()
