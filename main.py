import os
import json
import asyncio
import random
import re
import httpx
from urllib.parse import urlparse
from typing import Optional, List, Dict, Any, Set
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
# Ensure keywords.py is present in your repo
from keywords import MISSION_KEYWORDS, CROSS_CUTTING_KEYWORDS

# --- SETUP & CONFIG ---
load_dotenv()

# API KEYS
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_SEARCH_KEY = os.getenv("GOOGLE_SEARCH_KEY")
GOOGLE_SEARCH_CX = os.getenv("GOOGLE_SEARCH_CX")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1L9NwFZK_9PjZYe8StdLTvisTkbA_Lu_86NQSmqHGXaE/"

# --- APP INITIALIZATION ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CLIENT INIT ---
client = OpenAI(api_key=OPENAI_API_KEY)

# --- DATABASE CONNECTION ---
def connect_db():
    raw_creds = os.getenv("GOOGLE_CREDENTIALS")
    if not raw_creds:
        print("❌ GOOGLE_CREDENTIALS missing.")
        return None
    try:
        creds_dict = json.loads(raw_creds)
        scope = [
            "https://spreadsheets.google.com/feeds", 
            "https://www.googleapis.com/auth/spreadsheets", 
            "https://www.googleapis.com/auth/drive"
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        g_client = gspread.authorize(creds)
        return g_client.open_by_url(SHEET_URL).sheet1
    except Exception as e:
        print(f"❌ DB Error: {e}")
        return None

def ensure_sheet_headers(sheet):
    """Ensures headers exist and include Source_Country."""
    expected = [
        "Title", "Score", "Hook", "URL", "Mission", "Lenses", 
        "Score_Evocativeness", "Score_Novelty", "Score_Evidence", 
        "Source_Country", # <--- NEW FEATURE
        "User_Rating", "User_Status", "User_Comment", "Shareable", "Feedback"
    ]
    try:
        existing = sheet.row_values(1)
        if existing != expected:
            sheet.resize(rows=1000, cols=len(expected))
            sheet.update(range_name='A1', values=[expected])
    except: pass

# --- PROMPT HELPERS (Restored from your original code) ---

def get_learning_examples():
    """Fetches high-quality examples (4+ Stars) to teach the AI."""
    try:
        sheet = connect_db()
        if not sheet: return ""
        records = sheet.get_all_records()
        good = [r for r in records if str(r.get('User_Rating','')).isdigit() and int(r.get('User_Rating',0)) >= 4]
        if not good: return ""
        examples = random.sample(good, k=min(3, len(good)))
        prompt = "### USER'S GOLD STANDARD EXAMPLES (EMULATE THESE):\n"
        for ex in examples:
            prompt += f"- Title: {ex.get('Title')}\n  Hook: {ex.get('Hook')}\n  Note: {ex.get('User_Comment','')}\n"
        return prompt
    except: return ""

def get_mission_keywords(message: str):
    """Restored the complex keyword rotator."""
    rng = random.Random()
    prompt_parts = ["### MISSION KEYWORD HINTS (ROTATE ACROSS THESE):"]
    for mission, keywords in MISSION_KEYWORDS.items():
        selected = rng.sample(keywords, min(4, len(keywords)))
        prompt_parts.append(f"- {mission}: {', '.join(selected)}")
    
    # Add adjacent topics if applicable
    tokens = [t for t in re.split(r"[^a-z0-9]+", message.lower()) if len(t) >= 4]
    related = []
    for kw in CROSS_CUTTING_KEYWORDS:
        if any(t in kw.lower() for t in tokens): related.append(kw)
    
    if related:
        prompt_parts.append(f"- ADJACENT TOPICS: {', '.join(related[:5])}")
        
    return "\n".join(prompt_parts)

# --- SEARCH ENGINE ---

async def perform_google_search(query):
    if not GOOGLE_SEARCH_KEY or not GOOGLE_SEARCH_CX: return "System Error: Keys missing."
    print(f"🔍 Searching: {query}")
    async with httpx.AsyncClient() as http_client:
        try:
            params = {"key": GOOGLE_SEARCH_KEY, "cx": GOOGLE_SEARCH_CX, "q": query, "num": 8, "dateRestrict": "m1"}
            resp = await http_client.get("https://www.googleapis.com/customsearch/v1", params=params)
            data = resp.json()
            items = data.get("items", [])
            if not items: return "No results found."
            return "\n\n".join([f"Title: {i.get('title')}\nLink: {i.get('link')}\nSnippet: {i.get('snippet','')}\nDate: {i.get('pagemap',{}).get('metatags', [{}])[0].get('article:published_time', 'Unknown')}" for i in items])
        except Exception as e: return f"Search Error: {str(e)}"

# --- ENDPOINTS ---

class ChatRequest(BaseModel):
    message: str
    tech_mode: bool = False

class SaveSignalRequest(BaseModel):
    title: str
    score: int
    hook: str
    final_url: str
    source_country: str = "Global" # <--- NEW FEATURE
    mission: str = "Unspecified"
    lenses: Optional[str] = ""
    score_evocativeness: Optional[int] = 0
    score_novelty: Optional[int] = 0
    score_evidence: Optional[int] = 0
    user_rating: Optional[int] = 3
    user_status: Optional[str] = "Pending"
    user_comment: Optional[str] = ""
    shareable: Optional[str] = "Maybe"

@app.get("/")
def health_check():
    return {"status": "online", "message": "Signal Scout (Maximalist V3) is Running"}

@app.get("/api/saved")
def get_saved_signals():
    sheet = connect_db()
    if not sheet: return []
    try: return sheet.get_all_records()
    except: return []

@app.post("/api/save")
def save_signal(signal: SaveSignalRequest):
    """
    Saves a signal to Google Sheets with SAFE MERGING.
    If the row exists, it prioritizes existing data over empty/default incoming data.
    """
    sheet = connect_db()
    if not sheet:
        raise HTTPException(status_code=500, detail="Database Unavailable")
    
    ensure_sheet_headers(sheet)

    try:
        # 1. Fetch all records to check for duplicates
        records = sheet.get_all_records()
        target_url = signal.final_url.strip().lower()
        row_idx = None
        existing_record = {}
        
        for i, r in enumerate(records):
            # +2 because Google Sheets is 1-indexed and has a header row
            if str(r.get('URL','')).strip().lower() == target_url:
                row_idx = i + 2 
                existing_record = r
                break
        
        # 2. DEFENSIVE MERGE LOGIC
        # If the signal exists, use the existing data if the new data is missing/empty.
        if row_idx:
            # Logic: New Value OR Old Value (if New is empty)
            final_title = signal.title or existing_record.get('Title', '')
            final_score = signal.score if signal.score != 0 else existing_record.get('Score', 0)
            final_hook = signal.hook or existing_record.get('Hook', '')
            final_mission = signal.mission or existing_record.get('Mission', '')
            final_lenses = signal.lenses or existing_record.get('Lenses', '')
            
            # Sub-scores
            final_evoc = signal.score_evocativeness if signal.score_evocativeness != 0 else existing_record.get('Score_Evocativeness', 0)
            final_novel = signal.score_novelty if signal.score_novelty != 0 else existing_record.get('Score_Novelty', 0)
            final_evidence = signal.score_evidence if signal.score_evidence != 0 else existing_record.get('Score_Evidence', 0)
            
            # Country
            final_country = signal.source_country if signal.source_country != "Global" else existing_record.get('Source_Country', 'Global')

            # User Data (Always prefer new user input if provided, otherwise keep old)
            final_rating = signal.user_rating if signal.user_rating != 3 else existing_record.get('User_Rating', 3)
            final_status = signal.user_status if signal.user_status != "Pending" else existing_record.get('User_Status', 'Pending')
            final_comment = signal.user_comment or existing_record.get('User_Comment', '')
            final_shareable = signal.shareable if signal.shareable != "Maybe" else existing_record.get('Shareable', 'Maybe')

            # Reconstruct the row with SAFE data
            row_data = [
                final_title, final_score, final_hook, signal.final_url, 
                final_mission, final_lenses, 
                final_evoc, final_novel, final_evidence, 
                final_country, 
                final_rating, final_status, final_comment, final_shareable, ""
            ]
            
            print(f"♻️ Safe Update at row {row_idx}")
            sheet.update(range_name=f"A{row_idx}:O{row_idx}", values=[row_data])
            return {"status": "updated"}

        else:
            # 3. NEW ROW (Just append what we have)
            row_data = [
                signal.title, signal.score, signal.hook, signal.final_url, 
                signal.mission, signal.lenses, 
                signal.score_evocativeness, signal.score_novelty, signal.score_evidence, 
                signal.source_country, 
                signal.user_rating, signal.user_status, signal.user_comment, signal.shareable, ""
            ]
            sheet.append_row(row_data)
            return {"status": "saved"}
            
    except Exception as e:
        print(f"Save Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    print(f"💬 Query: {req.message} | Tech Mode: {req.tech_mode}")
    if not ASSISTANT_ID: raise HTTPException(status_code=500, detail="Missing ASSISTANT_ID")

    # --- RESTORING THE MASSIVE PROMPT CONSTRUCTION ---
    learning_prompt = get_learning_examples()
    mission_prompt = get_mission_keywords(req.message)
    
    # Rebuilding the exact logic from your original code
    prompt = req.message
    prompt += "\n\nROLE: You are Nesta's Discovery Hub Lead Foresight Researcher. Operate as a research engine (not a writer) and use British English."
    prompt += "\n\nNON-NEGOTIABLE WORKFLOW: You have no memory. You MUST perform fresh 'perform_web_search' calls. If no direct article URL is found, discard the candidate."
    
    prompt += "\n\nTOOL CONTRACT (display_signal_card): title (<=8 words), score (0-100), source_country (e.g., 'UK', 'Estonia'), "
    prompt += "hook (75-100 words using the Deep Hook 3-sentence format), final_url, mission (choose from list)."
    
    prompt += "\n\nSCORING RUBRIC (0-10):"
    prompt += "\n- Novelty: Distance from mainstream (BBC=2, Reddit/arXiv=8)."
    prompt += "\n- Evidence: Reality factor (Concept=1, Pilot/Law=9)."
    prompt += "\n- Evocativeness: The 'What the hell?' factor."

    prompt += """
    \nSYSTEM PROTOCOL (THE FRICTION METHOD):
    1) Build 3–5 high-friction queries (e.g., Topic + 'unregulated', 'lawsuit', 'homebrew', 'black market').
    2) Perform 'perform_web_search' for each.
    3) THE KILL COMMITTEE: Reject generic 'Future of X' articles. Reject homepages. Keep only deep links.
    4) HYPE CHECK: If Novelty < 4, discard unless Evidence > 8.
    5) Repeat until you have N verified signals.
    """
    
    prompt += f"\n\nPRIMARY TOPIC: \"{req.message.strip()}\""
    
    if req.tech_mode:
        prompt += "\n\nCONSTRAINT: TECH MODE ON. Search ONLY for Hard Tech (Hardware, Biotech, Materials, Code)."
    
    if learning_prompt:
        prompt += f"\n\n{learning_prompt}\nINSTRUCTION: Emulate the taste profile of the examples above."
        
    if mission_prompt:
        prompt += f"\n\n{mission_prompt}\nINSTRUCTION: Rotate through these keywords to find diverse signals."

    # --- EXECUTION LOOP ---
    try:
        thread = await asyncio.to_thread(client.beta.threads.create)
        await asyncio.to_thread(client.beta.threads.messages.create, thread_id=thread.id, role="user", content=prompt)
        run = await asyncio.to_thread(client.beta.threads.runs.create, thread_id=thread.id, assistant_id=ASSISTANT_ID)

        accumulated_signals = []
        while True:
            run_status = await asyncio.to_thread(client.beta.threads.runs.retrieve, thread_id=thread.id, run_id=run.id)
            
            if run_status.status == 'requires_action':
                tool_calls = run_status.required_action.submit_tool_outputs.tool_calls
                tool_outputs = []
                for tool in tool_calls:
                    if tool.function.name == "perform_web_search":
                        q = json.loads(tool.function.arguments).get("query")
                        res = await perform_google_search(q)
                        tool_outputs.append({"tool_call_id": tool.id, "output": res})
                    
                    elif tool.function.name == "display_signal_card":
                        data = json.loads(tool.function.arguments)
                        # Normalize keys and capture country
                        sig = {
                            "title": data.get("title", "Untitled"),
                            "score": data.get("score", 0),
                            "hook": data.get("hook", ""),
                            "final_url": data.get("final_url", "#"),
                            "source_country": data.get("source_country", "Global"), # <--- CAPTURE COUNTRY
                            "mission": data.get("mission", "General"),
                            "score_novelty": data.get("score_novelty", 0),
                            "score_evidence": data.get("score_evidence", 0),
                            "score_evocativeness": data.get("score_evocativeness", 0)
                        }
                        accumulated_signals.append(sig)
                        tool_outputs.append({"tool_call_id": tool.id, "output": json.dumps({"status": "displayed"})})
                
                await asyncio.to_thread(client.beta.threads.runs.submit_tool_outputs, thread_id=thread.id, run_id=run.id, tool_outputs=tool_outputs)
            
            elif run_status.status == 'completed':
                return {"signals": accumulated_signals}
            elif run_status.status in ['failed', 'expired', 'cancelled']:
                raise HTTPException(status_code=500, detail=f"AI Failed: {run_status.last_error}")
            
            await asyncio.sleep(1)
            
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
