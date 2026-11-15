"""Clip Studio: Streamlit front-end for the clip pipeline and YouTube publishing."""
from __future__ import annotations

import hmac
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

from core import config, publisher
from core.captions import CAPTION_STYLES
from core.jobs import JOBS
from core.library import load_library, mark_published
from core.models import JobSettings, MediaSource

LANGUAGES = {
    "auto": "Auto-detect", "en": "English", "es": "Spanish", "fr": "French",
    "de": "German", "pt": "Portuguese", "hi": "Hindi", "ar": "Arabic",
}
MODEL_SIZES = ["tiny", "base", "small", "medium"]

st.set_page_config(page_title="Clip Studio", page_icon="🎬", layout="centered")

CSS = """
<style>
#MainMenu, footer {visibility: hidden;}
.block-container {padding-top: 1.5rem; padding-bottom: 3rem; max-width: 900px;}
.hero {background: linear-gradient(135deg, #7C5CFF, #22D3EE); -webkit-background-clip: text;
       background-clip: text; color: transparent; font-size: 2.1rem; font-weight: 800; margin: 0;}
.subtle {opacity: .7; margin-top: .25rem;}
.stTabs [data-baseweb="tab-list"] {gap: 6px; overflow-x: auto;}
.stButton > button, .stLinkButton > a {border-radius: 12px; font-weight: 600;}
</style>
"""


def require_login() -> None:
    """Simple shared-password gate. Leave APP_PASSWORD empty to disable (local use only)."""
    if not config.APP_PASSWORD or st.session_state.get("authenticated"):
        return
    st.markdown('<p class="hero">Clip Studio</p>', unsafe_allow_html=True)
    with st.form("login"):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Unlock")
    if submitted:
        if hmac.compare_digest(password.encode(), config.APP_PASSWORD.encode()):
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("Incorrect password.")
    st.stop()


def handle_oauth_callback() -> None:
    params = st.query_params
    if "code" not in params or "state" not in params:
        return
    try:
        publisher.finish_authorization(params["code"], params["state"])
        st.toast("YouTube connected", icon="✅")
    except Exception as exc:
        st.error(f"YouTube connection failed: {exc}")
    finally:
        st.query_params.clear()


# ---------- Settings tab ----------

def render_settings_tab() -> None:
    st.subheader("Clip settings")
    st.slider(
        "Clip length (seconds)", min_value=30, max_value=60, value=(30, 60), key="clip_range",
        help="Highlights are chosen between the lower and upper bound.",
    )
    st.slider("Clips to generate", 1, 10, 5, key="num_clips")
    st.selectbox(
        "Caption style", list(CAPTION_STYLES),
        format_func=lambda k: CAPTION_STYLES[k].label, key="caption_style",
    )
    st.toggle(
        "Face-aware 9:16 crop", value=True, key="face_crop",
        help="Centres the vertical crop on the largest face. Turn off for a plain centre crop.",
    )
    st.divider()
    st.subheader("Transcription")
    st.select_slider("Model (speed ↔ accuracy)", options=MODEL_SIZES, value="small", key="model_size")
    st.selectbox("Spoken language", list(LANGUAGES), format_func=LANGUAGES.get, key="language")
    st.caption("Output: 1080 × 1920 MP4 (9:16), H.264 video and AAC audio.")


def current_settings() -> JobSettings:
    low, high = st.session_state.get("clip_range", (30, 60))
    language = st.session_state.get("language", "auto")
    return JobSettings(
        min_duration=low,
        max_duration=high,
        num_clips=st.session_state.get("num_clips", 5),
        caption_style=st.session_state.get("caption_style", "bold_pop"),
        language=None if language == "auto" else language,
        model_size=st.session_state.get("model_size", "small"),
        face_crop=st.session_state.get("face_crop", True),
    )


# ---------- Input tab ----------

def _build_source(url: str, upload) -> MediaSource | None:
    url = url.strip()
    if url:
        if not re.match(r"^https?://", url):
            st.error("Enter a full link that starts with https://")
            return None
        return MediaSource(kind="url", value=url, label=url)
    if upload is not None:
        target_dir = config.UPLOAD_DIR / uuid.uuid4().hex
        target_dir.mkdir(parents=True)
        safe_name = re.sub(r"[^\w.\-]", "_", Path(upload.name).name)
        path = target_dir / safe_name
        path.write_bytes(upload.getbuffer())
        return MediaSource(kind="file", value=str(path), label=upload.name)
    st.error("Paste a link or upload a file first.")
    return None


def render_input_tab() -> None:
    st.subheader("Source video")
    mode = st.radio("Source", ["Paste a link", "Upload a file"], horizontal=True, label_visibility="collapsed")
    url, upload = "", None
    if mode == "Paste a link":
        url = st.text_input("Video URL", placeholder="https://…")
    else:
        upload = st.file_uploader("Video file", type=["mp4", "mov", "mkv", "webm"])
    st.caption("Only process videos you own or have the rights to use.")

    if st.button("Generate shorts", type="primary"):
        source = _build_source(url, upload)
        if source is not None:
            job_id = JOBS.submit(source, current_settings())
            st.session_state["job_picker"] = job_id
            st.toast("Job queued. Check the Processing tab.")


# ---------- Processing tab ----------

@st.fragment(run_every=2)
def render_status() -> None:
    jobs = JOBS.recent()
    if not jobs:
        st.info("No jobs yet. Start one from the Input tab.")
        return

    ids = [job.id for job in jobs]
    labels = {job.id: f"{job.status.upper()} · {job.source.label[:60]}" for job in jobs}
    choice = st.selectbox("Job", ids, format_func=labels.get, key="job_picker")
    snap = JOBS.get(choice).snapshot()

    st.progress(snap["progress"], text=f"{snap['stage']} · {round(snap['progress'] * 100)}%")
    if snap["status"] == "done":
        st.success(f"{snap['clip_count']} clip(s) ready. Open the Library tab to preview and publish.")
    elif snap["status"] == "failed":
        st.error(snap["error"] or "Unknown error")
    elif snap["status"] == "queued":
        st.caption("Queued. Jobs run one at a time.")

    with st.expander("Logs", expanded=True):
        st.code("\n".join(snap["logs"][-200:]) or "Waiting for logs…", language=None)


# ---------- Library tab ----------

def render_youtube_connection() -> None:
    if not config.YOUTUBE_CLIENT_SECRETS.exists():
        st.warning("YouTube publishing is off. Add client_secret.json (see the README).")
        return
    if publisher.is_connected():
        left, right = st.columns([3, 1])
        left.success("YouTube connected")
        if right.button("Disconnect"):
            publisher.disconnect()
            st.session_state.pop("youtube_auth_url", None)
            st.rerun()
        return

    st.info("Connect your YouTube channel once to enable publishing.")
    if st.button("Connect YouTube"):
        try:
            st.session_state["youtube_auth_url"] = publisher.start_authorization()
        except Exception as exc:
            st.error(str(exc))
    if url := st.session_state.get("youtube_auth_url"):
        st.link_button("Continue to Google sign-in", url, type="primary")


def _fmt_created(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%b %d, %H:%M")
    except ValueError:
        return iso


def render_publish_controls(job_id: str, clip: dict, key: str, title: str, description: str) -> None:
    privacy = st.selectbox(
        "Visibility", ["private", "unlisted", "public"], key=f"{key}-privacy",
        help="Google keeps uploads from unverified API projects private until the project is audited.",
    )
    schedule = st.toggle("Schedule publish time", key=f"{key}-schedule")
    publish_at = None
    if schedule:
        tz = ZoneInfo(config.APP_TIMEZONE)
        default = datetime.now(tz) + timedelta(days=1)
        day = st.date_input("Publish date", default.date(), key=f"{key}-date")
        clock = st.time_input("Publish time", default.replace(minute=0, second=0, microsecond=0).time(), key=f"{key}-time")
        publish_at = datetime.combine(day, clock, tzinfo=tz)
        st.caption(f"Goes live {publish_at:%b %d, %H:%M %Z}. It stays private until then.")

    if st.button("Publish to YouTube", key=f"{key}-publish", type="primary"):
        _publish(job_id, clip, title, description, privacy, publish_at)


def _publish(job_id: str, clip: dict, title: str, description: str, privacy: str, publish_at: datetime | None) -> None:
    if not publisher.is_connected():
        st.error("Connect YouTube first (above).")
        return
    if publish_at and publish_at <= datetime.now(publish_at.tzinfo) + timedelta(minutes=15):
        st.error("Scheduled time must be at least 15 minutes in the future.")
        return
    try:
        with st.spinner("Uploading to YouTube…"):
            video_id = publisher.upload_video(
                Path(clip["path"]), title=title, description=description,
                privacy=privacy, publish_at=publish_at,
            )
    except Exception as exc:
        st.error(f"Upload failed: {exc}")
        return
    mark_published(job_id, clip["index"], video_id)
    st.success("Uploaded to YouTube.")
    st.rerun()


def render_clip_card(job_id: str, clip: dict) -> None:
    key = f"{job_id}-{clip['index']}"
    path = Path(clip["path"])
    with st.container(border=True):
        if not path.exists():
            st.warning("This clip file is missing from disk.")
            return
        left, right = st.columns([1, 1.2])
        with left:
            st.video(str(path))
        with right:
            title = st.text_input("Title", value=clip["title"], key=f"{key}-title", max_chars=100)
            description = st.text_area("Description", value=clip["description"], key=f"{key}-desc", height=90)
            st.download_button(
                "Download MP4", path.read_bytes(), file_name=f"{key}.mp4",
                mime="video/mp4", key=f"{key}-download",
            )
            if clip.get("youtube_id"):
                st.link_button("Open on YouTube", f"https://youtu.be/{clip['youtube_id']}")
            else:
                render_publish_controls(job_id, clip, key, title, description)


def render_library_tab() -> None:
    render_youtube_connection()
    st.divider()
    items = load_library()
    if not items:
        st.info("Finished jobs appear here.")
        return
    for position, item in enumerate(items):
        header = f"{_fmt_created(item['created'])} · {item['source_label'][:60]} · {len(item['clips'])} clips"
        with st.expander(header, expanded=position == 0):
            for clip in item["clips"]:
                render_clip_card(item["job_id"], clip)


# ---------- App entry point ----------

def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    require_login()
    handle_oauth_callback()

    st.markdown(
        '<p class="hero">Clip Studio</p>'
        '<p class="subtle">Turn long videos into captioned vertical shorts, then publish or schedule them.</p>',
        unsafe_allow_html=True,
    )
    tab_input, tab_settings, tab_status, tab_library = st.tabs(["Input", "Settings", "Processing", "Library"])
    with tab_settings:
        render_settings_tab()  # rendered first so Input can read the values
    with tab_input:
        render_input_tab()
    with tab_status:
        render_status()
    with tab_library:
        render_library_tab()


main()
