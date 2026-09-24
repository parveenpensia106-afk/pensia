import os, json, uuid
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from generators import create_pdf, create_docx, create_xlsx
from transcript import transcribe_audio_file, youtube_transcript

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR, OUTPUT_DIR = BASE_DIR/"uploads", BASE_DIR/"output"
UPLOAD_DIR.mkdir(exist_ok=True); OUTPUT_DIR.mkdir(exist_ok=True)

key = os.getenv("OPENAI_API_KEY")
if not key: raise RuntimeError("OPENAI_API_KEY is missing in .env")
client = OpenAI(api_key=key)
app = FastAPI(title="AI Video Notes Maker")

# Serve /static/style.css etc. Without this, FastAPI returns 404 for static files.
app.mount("/static", StaticFiles(directory=str(BASE_DIR/"static")), name="static")

@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE_DIR/"templates/index.html").read_text(encoding="utf-8")

@app.post("/generate")
async def generate_notes(youtube_url: str=Form(""), language: str=Form("English"),
                         notes_type: str=Form("Detailed Notes"),
                         video: UploadFile|None=File(None)):
    try:
        if youtube_url.strip():
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
            raise HTTPException(400, "Enter a YouTube URL or upload a video/audio file.")
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
        # NOTE: "gpt-5.6-luna" is not a real OpenAI model name and will fail.
        # Default to a real, current model. Override with OPENAI_TEXT_MODEL env var if needed.
        model_name = os.getenv("OPENAI_TEXT_MODEL", "gpt-4o-mini")
        r = client.responses.create(model=model_name, input=prompt)
        raw = r.output_text.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"): raw = raw[4:].strip()
        notes = json.loads(raw)

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
