import os
from pathlib import Path
from openai import OpenAI

client=OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def transcribe_audio_file(path: Path)->str:
    with path.open("rb") as f:
        r=client.audio.transcriptions.create(
            model=os.getenv("OPENAI_TRANSCRIBE_MODEL","gpt-4o-mini-transcribe"), file=f)
    return r.text

def youtube_transcript(url:str)->str:
    from youtube_transcript_api import YouTubeTranscriptApi
    vid=extract_video_id(url)
    if not vid: raise ValueError("Invalid YouTube URL.")
    api=YouTubeTranscriptApi()
    items=api.list(vid)
    chosen=next((x for x in items if not x.is_generated),None)
    if chosen is None: chosen=next((x for x in items if x.is_generated),None)
    if chosen is None: raise ValueError("No accessible captions. Upload video/audio instead.")
    return "\n".join(x.text for x in chosen.fetch())

def extract_video_id(url):
    from urllib.parse import urlparse,parse_qs
    p=urlparse(url)
    if p.hostname in {"youtu.be","www.youtu.be"}: return p.path.strip("/").split("/")[0]
    if p.hostname and "youtube.com" in p.hostname:
        if p.path=="/watch": return parse_qs(p.query).get("v",[None])[0]
        if p.path.startswith("/shorts/"): return p.path.split("/")[2]
        if p.path.startswith("/embed/"): return p.path.split("/")[2]
    return None
