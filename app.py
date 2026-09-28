import os, json, uuid
from pathlib import Path
from dotenv import load_dotenv
_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH, override=True)
print("[env] .env path:", _ENV_PATH, "| exists:", _ENV_PATH.exists())
print("[env] YT_COOKIES_BROWSER =", repr(os.getenv("YT_COOKIES_BROWSER")))
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import anthropic
from generators import create_pdf, create_docx, create_xlsx
from transcript import transcribe_audio_file, youtube_transcript

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR, OUTPUT_DIR = BASE_DIR/"uploads", BASE_DIR/"output"
UPLOAD_DIR.mkdir(exist_ok=True); OUTPUT_DIR.mkdir(exist_ok=True)

def _find_key():
    k = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not k:
        o = os.getenv("OPENAI_API_KEY", "").strip()
        if o.startswith("sk-ant-"):   # user pasted a Claude key in the old variable
            k = o
    return k

key = _find_key()
if not key: raise RuntimeError("ANTHROPIC_API_KEY is missing in .env")
client = anthropic.Anthropic(api_key=key)
app = FastAPI(title="AI Video Notes Maker")

# Serve /static/style.css etc. Without this, FastAPI returns 404 for static files.
app.mount("/static", StaticFiles(directory=str(BASE_DIR/"static")), name="static")

def parse_json(raw: str):
    """Claude kabhi ```json fences ya extra text de deta hai; sirf { ... } nikaalo."""
    i, j = raw.find("{"), raw.rfind("}")
    if i == -1 or j == -1: raise ValueError("Model did not return JSON. Try again.")
    return json.loads(raw[i:j+1])

@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE_DIR/"templates/index.html").read_text(encoding="utf-8")

@app.post("/generate")
async def generate_notes(youtube_url: str=Form(""), language: str=Form("English"),
                         notes_type: str=Form("Detailed Notes"),
                         transcript_text: str=Form(""),
                         video: UploadFile|None=File(None)):
    try:
        if transcript_text.strip():
            transcript = transcript_text.strip()
        elif youtube_url.strip():
            transcript = youtube_transcript(youtube_url.strip())
        elif video and video.filename:
            ext = Path(video.filename).suffix.lower()
            if ext not in {".mp3",".mp4",".m4a",".wav",".webm",".mpeg",".mpga"}:
                raise HTTPException(400, "Unsupported video/audio format.")
            path = UPLOAD_DIR/(uuid.uuid4().hex+ext)
            with path.open("wb") as f:
                while chunk := await video.read(1024*1024): f.write(chunk)
            transcript = transcribe_audio_file(path)
        else:
            raise HTTPException(400, "Enter a YouTube URL, paste a transcript, or upload a video/audio file.")
        if not transcript.strip(): raise HTTPException(400, "No transcript was obtained.")

        prompt = f"""Create educational notes from this transcript.
Language: {language}
Format: {notes_type}
Return ONLY valid JSON:
{{"title":"title","summary":"summary","key_points":["point"],
"detailed_notes":[{{"heading":"topic","content":"explanation"}}],
"important_questions":["question"],
"mcqs":[{{"question":"q","options":["A","B","C","D"],"answer":"A"}}]}}
Be accurate and do not invent facts.
TRANSCRIPT:
{transcript}"""
        model_name = os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-5"
        r = client.messages.create(model=model_name, max_tokens=8000,
                                   messages=[{"role": "user", "content": prompt}])
        raw = "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip()
        notes = parse_json(raw)

        jid = uuid.uuid4().hex
        pdf, docx, xlsx = OUTPUT_DIR/f"{jid}.pdf", OUTPUT_DIR/f"{jid}.docx", OUTPUT_DIR/f"{jid}.xlsx"
        create_pdf(notes,pdf); create_docx(notes,docx); create_xlsx(notes,xlsx)
        return {"success":True,"title":notes.get("title","AI Notes"),
                "summary":notes.get("summary",""),
                "files":{"pdf":f"/download/{jid}.pdf","word":f"/download/{jid}.docx","excel":f"/download/{jid}.xlsx"}}
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, str(e))

@app.get("/download/{filename}")
def download(filename: str):
    p=OUTPUT_DIR/filename
    if not p.exists(): raise HTTPException(404,"File not found")
    return FileResponse(p, filename=filename)
