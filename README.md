# AI Video Notes Maker

## Windows setup
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

Copy `.env.example` to `.env` and add your OpenAI API key.

Run:
uvicorn app:app --reload

Open:
http://127.0.0.1:8000

The app accepts YouTube captions or uploaded audio/video and generates PDF, DOCX and XLSX.
