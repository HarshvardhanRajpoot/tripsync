"""
Finds which Gemini models work with YOUR key.

Run from the backend folder (venv active):
    python check_gemini.py

It never prints your key. For each text model it sends one tiny request and
prints OK / the short error, plus how long it took. Then it tells you what to
put in backend/.env.
"""
import os
import time

from dotenv import load_dotenv

load_dotenv()
key = os.getenv("GEMINI_API_KEY")
if not key or key.startswith("your"):
    raise SystemExit("GEMINI_API_KEY is missing in backend/.env (or still the placeholder).")

from google import genai
from google.genai import types

client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=20_000))

# 1. which models can this key see?
try:
    models = list(client.models.list())
except Exception as e:
    raise SystemExit(f"Could not list models: {str(e)[:200]}\nCheck the key and your internet connection.")

names = []
for m in models:
    actions = getattr(m, "supported_actions", None) or []
    name = (m.name or "").removeprefix("models/")
    if "generateContent" in actions and "flash" in name and not any(
        bad in name for bad in ("image", "tts", "audio", "live", "embedding", "robotics", "computer", "native")
    ):
        names.append(name)

names = sorted(set(names))[:10]
print(f"Text models visible to your key (testing up to 10): {len(names)}\n")

# 2. try each one with a tiny JSON request, like the planner does
working = []
for name in names:
    start = time.time()
    try:
        res = client.models.generate_content(
            model=name,
            contents='Reply with JSON only: {"ok": true}',
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
        )
        secs = time.time() - start
        ok = bool((res.text or "").strip())
        print(f"  {'OK  ' if ok else 'EMPTY'} {name:<40} {secs:4.1f}s")
        if ok:
            working.append((secs, name))
    except Exception as e:
        msg = " ".join(str(e).split())
        short = "503 busy (high demand)" if "503" in msg else "429 quota/rate limit" if "429" in msg \
            else "404 not available" if "404" in msg else msg[:70]
        print(f"  FAIL  {name:<40} {short}")
    time.sleep(1.5)   # stay under free-tier per-minute limits

# 3. recommendation
print()
if not working:
    print("No model worked right now. If most say '503 busy', wait 10-15 minutes and run this again.")
    print("If they say '429', you hit the free-tier limit: wait a minute, or check AI Studio usage.")
else:
    working.sort()
    best = working[0][1]
    print("Put this in backend/.env, then restart the backend:")
    print(f"  GEMINI_MODEL={best}")
    if len(working) > 1:
        print(f"  GEMINI_FALLBACK_MODEL={working[1][1]}")
