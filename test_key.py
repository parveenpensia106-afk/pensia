"""Run:  python test_key.py   (same folder jahan .env hai)"""
import os
from pathlib import Path
from dotenv import load_dotenv
import anthropic

env = Path(__file__).resolve().parent / ".env"
load_dotenv(env, override=True)
print(".env found:", env.exists(), "->", env)

key = ""
for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
    k = (os.getenv(name) or "").strip().strip('"').strip("'").strip()
    if k.startswith("sk-ant-") and "YOUR" not in k.upper():
        key = k; print(f"using {name}: {k[:12]}...{k[-4:]}  length={len(k)}"); break
if not key:
    raise SystemExit("Koi valid sk-ant- key .env mein nahi mili.")

try:
    r = anthropic.Anthropic(api_key=key).messages.create(
        model=os.getenv("ANTHROPIC_MODEL") or "claude-haiku-4-5-20251001",
        max_tokens=20, messages=[{"role": "user", "content": "Say OK"}])
    print("✅ KEY SAHI HAI. Claude ne kaha:", r.content[0].text)
except anthropic.AuthenticationError:
    print("❌ Key invalid/revoked/galat copy. console.anthropic.com se NAYI key banao.")
except anthropic.PermissionDeniedError as e:
    print("❌ Permission problem:", e)
except anthropic.NotFoundError:
    print("❌ Model name galat hai. .env mein ANTHROPIC_MODEL=claude-haiku-4-5-20251001 try karo.")
except anthropic.BadRequestError as e:
    print("❌ Request problem (billing/credits ho sakta hai):", e)
except Exception as e:
    print("❌ Other error:", type(e).__name__, e)
