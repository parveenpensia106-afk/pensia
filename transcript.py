import os, re, glob, tempfile, shutil
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MAX_AUDIO_BYTES = 24 * 1024 * 1024  # OpenAI transcription limit is 25 MB


def transcribe_audio_file(path: Path) -> str:
    with path.open("rb") as f:
        r = client.audio.transcriptions.create(
            model=os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe"), file=f)
    return r.text


def extract_video_id(url):
    p = urlparse(url)
    if p.hostname in {"youtu.be", "www.youtu.be"}:
        return p.path.strip("/").split("/")[0]
    if p.hostname and "youtube.com" in p.hostname:
        if p.path == "/watch":
            return parse_qs(p.query).get("v", [None])[0]
        if p.path.startswith(("/shorts/", "/embed/", "/live/")):
            return p.path.split("/")[2]
    return None


# ---------- Method 1: youtube-transcript-api (optional proxy) ----------
def _via_transcript_api(vid: str) -> str:
    from youtube_transcript_api import YouTubeTranscriptApi
    proxy = os.getenv("YT_PROXY_URL", "").strip()
    if proxy:
        from youtube_transcript_api.proxies import GenericProxyConfig
        api = YouTubeTranscriptApi(proxy_config=GenericProxyConfig(http_url=proxy, https_url=proxy))
    else:
        api = YouTubeTranscriptApi()
    items = list(api.list(vid))
    chosen = next((x for x in items if not x.is_generated), None) or next(iter(items), None)
    if chosen is None:
        raise ValueError("No captions available.")
    return "\n".join(x.text for x in chosen.fetch())


# ---------- yt-dlp helpers ----------
def _ydl_opts(tmp: str, **extra):
    opts = {"quiet": True, "no_warnings": True, "outtmpl": os.path.join(tmp, "%(id)s.%(ext)s")}
    cookies = os.getenv("YT_COOKIES_FILE", "").strip()   # optional cookies.txt (Netscape format)
    proxy = os.getenv("YT_PROXY_URL", "").strip()
    browser = os.getenv("YT_COOKIES_BROWSER", "").strip().lower()  # firefox / chrome / edge / brave
    if cookies and os.path.exists(cookies):
        opts["cookiefile"] = cookies
    elif browser:
        opts["cookiesfrombrowser"] = (browser,)
    if proxy:
        opts["proxy"] = proxy
    opts.update(extra)
    return opts


def _clean_vtt(text: str) -> str:
    out, last = [], ""
    for line in text.splitlines():
        line = line.strip()
        if (not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE"))
                or "-->" in line or re.fullmatch(r"\d+", line)):
            continue
        line = re.sub(r"<[^>]+>", "", line).strip()
        if line and line != last:
            out.append(line); last = line
    return "\n".join(out)


# ---------- Method 2: yt-dlp subtitles ----------
def _via_ytdlp_subs(url: str) -> str:
    from yt_dlp import YoutubeDL
    tmp = tempfile.mkdtemp()
    try:
        opts = _ydl_opts(tmp, skip_download=True, writesubtitles=True, writeautomaticsub=True,
                         subtitleslangs=["en.*", "hi.*", "pa.*"], subtitlesformat="vtt")
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
        files = sorted(glob.glob(os.path.join(tmp, "*.vtt")))
        if not files:
            raise ValueError("No subtitles found via yt-dlp.")
        return _clean_vtt(Path(files[0]).read_text(encoding="utf-8", errors="ignore"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------- Method 3: yt-dlp audio -> OpenAI transcription ----------
def _via_audio(url: str) -> str:
    from yt_dlp import YoutubeDL
    tmp = tempfile.mkdtemp()
    try:
        opts = _ydl_opts(tmp, format="bestaudio[ext=m4a]/bestaudio[abr<=64]/bestaudio")
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
        files = [f for f in glob.glob(os.path.join(tmp, "*")) if os.path.isfile(f)]
        if not files:
            raise ValueError("Audio download failed.")
        f = Path(files[0])
        if f.stat().st_size > MAX_AUDIO_BYTES:
            raise ValueError("Video too long for audio fallback (over 24 MB audio).")
        return transcribe_audio_file(f)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _cookie_status() -> str:
    f = os.getenv("YT_COOKIES_FILE", "").strip()
    b = os.getenv("YT_COOKIES_BROWSER", "").strip()
    if f:
        return f"cookie file: {f} ({'found' if os.path.exists(f) else 'FILE NOT FOUND'})"
    if b:
        return f"browser cookies: {b}"
    return "NO COOKIES SET (.env not read or YT_COOKIES_BROWSER missing)"


def youtube_transcript(url: str) -> str:
    vid = extract_video_id(url)
    if not vid:
        raise ValueError("Invalid YouTube URL.")
    errors = []
    for name, fn, arg in (("captions API", _via_transcript_api, vid),
                          ("yt-dlp subtitles", _via_ytdlp_subs, url),
                          ("yt-dlp audio", _via_audio, url)):
        try:
            text = fn(arg)
            if text and text.strip():
                return text
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}: {(str(e).strip().splitlines() or ['blocked'])[0][:150]}")
    raise ValueError(
        "YouTube is blocking transcript/audio download from this IP. "
        "Fix: (1) paste the transcript in the box below, (2) upload the video/audio file, or "
        "(3) set YT_COOKIES_BROWSER=firefox (or YT_COOKIES_FILE / YT_PROXY_URL) in .env and restart. Details -> " + " | ".join(errors) + " || " + _cookie_status())
