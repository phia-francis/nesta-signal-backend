import os
import json
import asyncio
import random
import re
import httpx
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
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

client = OpenAI(api_key=OPENAI_API_KEY)

# --- DATABASE ---
def connect_db():
    raw_creds = os.getenv("GOOGLE_CREDENTIALS")
    if not raw_creds: return None
    try:
        creds_dict = json.loads(raw_creds)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        g_client = gspread.authorize(creds)
        return g_client.open_by_url(SHEET_URL).sheet1
    except: return None

def ensure_sheet_headers(sheet):
    expected = [
        "Title", "Score", "Hook", "URL", "Mission", "Lenses", 
        "Score_Evocativeness", "Score_Novelty", "Score_Evidence", 
        "Source_Country", 
        "User_Rating", "User_Status", "User_Comment", "Shareable", "Feedback"
    ]
    try:
        if sheet.row_values(1) != expected:
            sheet.resize(rows=1000, cols=len(expected))
            sheet.update(range_name='A1', values=[expected])
    except: pass

# --- LOGIC: RANDOM & PROMPTS ---
def generate_random_topic():
    mission = random.choice(list(MISSION_KEYWORDS.keys()))
    kw = random.sample(MISSION_KEYWORDS[mission], 2)
    return f"Future of {mission} involving {kw[0]} and {kw[1]}"

def get_mission_keywords(message: str):
    rng = random.Random()
    prompt = "### MISSION CONTEXT (Use these for diversity):"
    for m, k in MISSION_KEYWORDS.items():
        prompt += f"\n- {m}: {', '.join(rng.sample(k, min(4, len(k))))}"
    return prompt

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
            return "\n\n".join([f"Title: {i.get('title')}\nLink: {i.get('link')}\nSnippet: {i.get('snippet','')}" for i in items])
        except Exception as e: return f"Search Error: {str(e)}"

# --- ENDPOINTS ---
class ChatRequest(BaseModel):
    message: str = ""
    time_filter: str = "Past Month"
    tech_mode: bool = False
    source_types: List[str] = []
    signal_count: int = 3

class SaveSignalRequest(BaseModel):
    title: str
    score: int
    hook: str
    final_url: str
    source_country: str = "Global"
    mission: str = "Unspecified"
    lenses: Optional[str] = ""
    score_evocativeness: Optional[int] = 0
    score_novelty: Optional[int] = 0
    score_evidence: Optional[int] = 0
    user_rating: Optional[int] = 3
    user_status: Optional[str] = "Pending"
    user_comment: Optional[str] = ""     # Maps to 'User_Comment' column
    feedback: Optional[str] = ""         # Maps to 'Feedback' column (synced)
    shareable: Optional[str] = "Maybe"

@app.get("/")
def health(): return {"status": "online"}

@app.get("/api/saved")
def get_saved():
    sheet = connect_db()
    if not sheet: return []
    try: return sheet.get_all_records()
    except: return []

@app.post("/api/save")
def save_signal(signal: SaveSignalRequest):
    sheet = connect_db()
    if not sheet: raise HTTPException(500, "DB Error")
    ensure_sheet_headers(sheet)
    try:
        records = sheet.get_all_records()
        target_url = signal.final_url.strip().lower()
        row_idx = None
        existing = {}
        for i, r in enumerate(records):
            if str(r.get('URL','')).strip().lower() == target_url:
                row_idx = i + 2
                existing = r
                break
        
        # Use feedback field if provided, otherwise fallback to user_comment
        final_feedback = signal.feedback or signal.user_comment or ""

        # SAFE MERGE LOGIC
        if row_idx:
            # We prioritize the INCOMING data for editable fields (Shareable, Feedback)
            # We prioritize EXISTING data for static fields (Title, Hook) unless they were empty
            row = [
                signal.title or existing.get('Title',''),
                signal.score if signal.score != 0 else existing.get('Score',0),
                signal.hook or existing.get('Hook',''),
                signal.final_url,
                signal.mission or existing.get('Mission',''),
                signal.lenses or existing.get('Lenses',''),
                signal.score_evocativeness or existing.get('Score_Evocativeness',0),
                signal.score_novelty or existing.get('Score_Novelty',0),
                signal.score_evidence or existing.get('Score_Evidence',0),
                signal.source_country if signal.source_country != "Global" else existing.get('Source_Country','Global'),
                signal.user_rating, 
                signal.user_status,
                final_feedback, # Map to User_Comment
                signal.shareable, 
                final_feedback  # Map to Feedback
            ]
            sheet.update(range_name=f"A{row_idx}:O{row_idx}", values=[row])
            return {"status": "updated"}
        else:
            row = [
                signal.title, signal.score, signal.hook, signal.final_url, signal.mission, signal.lenses, 
                signal.score_evocativeness, signal.score_novelty, signal.score_evidence, signal.source_country, 
                signal.user_rating, signal.user_status, final_feedback, signal.shareable, final_feedback
            ]
            sheet.append_row(row)
            return {"status": "saved"}
    except Exception as e: raise HTTPException(500, str(e))

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    print(f"💬 Incoming: {req.message or 'RANDOM'} | Count: {req.signal_count}")
    if not ASSISTANT_ID: raise HTTPException(500, "No Assistant ID")

    topic = req.message if req.message.strip() else generate_random_topic()
    mission_data = get_mission_keywords(topic)

    # --- THE BRAIN: COMPLEX PROMPT CONSTRUCTION ---
    prompt = f"TARGET TOPIC: {topic}\n"
    prompt += f"GOAL: Find exactly {req.signal_count} unique, verified weak signals."
    
    prompt += """
    \nROLE: You are Nesta's Discovery Hub Lead Foresight Researcher.
    
    \nNON-NEGOTIABLE PROTOCOL:
    1. FRICTION SEARCH: Start by searching for '[Topic] + unregulated', '[Topic] + black market', '[Topic] + lawsuit'.
    2. FALLBACK SEARCH: If friction queries fail, pivot to specific technical queries (e.g., 'novel [Topic] pilot study'). DO NOT GIVE UP.
    3. KILL COMMITTEE: Reject generic opinion pieces. Reject homepages. Keep only specific articles/papers with direct URLs.
    """

    prompt += "\n\nTOOL CONTRACT (display_signal_card): title, score (0-100), source_country, hook, final_url, mission (Enum: A Fairer Start, A Healthy Life, A Sustainable Future), lenses."
    
    prompt += """
    \nSCORING RUBRIC (0-10):
    - Novelty: Distance from mainstream (BBC=Low, arXiv/Reddit=High).
    - Evidence: Reality factor (Concept=Low, Pilot/Law=High).
    - Evocativeness: The 'What the hell?' factor.
    """

    if req.tech_mode: prompt += "\nCONSTRAINT: TECH MODE ON. Ignore policy. Focus on Hardware/Biotech/Code."
    if req.source_types: prompt += f"\nCONSTRAINT: Prioritize sources: {', '.join(req.source_types)}."
    prompt += f"\n\n{mission_data}"

    try:
        thread = await asyncio.to_thread(client.beta.threads.create)
        await asyncio.to_thread(client.beta.threads.messages.create, thread_id=thread.id, role="user", content=prompt)
        run = await asyncio.to_thread(client.beta.threads.runs.create, thread_id=thread.id, assistant_id=ASSISTANT_ID)

        acc = []
        while True:
            status = await asyncio.to_thread(client.beta.threads.runs.retrieve, thread_id=thread.id, run_id=run.id)
            if status.status == 'requires_action':
                outputs = []
                for tool in status.required_action.submit_tool_outputs.tool_calls:
                    if tool.function.name == "perform_web_search":
                        q = json.loads(tool.function.arguments).get("query")
                        res = await perform_google_search(q)
                        outputs.append({"tool_call_id": tool.id, "output": res})
                    elif tool.function.name == "display_signal_card":
                        data = json.loads(tool.function.arguments)
                        acc.append({
                            "title": data.get("title","Untitled"), "score": data.get("score",0),
                            "hook": data.get("hook",""), "final_url": data.get("final_url","#"),
                            "source_country": data.get("source_country","Global"),
                            "mission": data.get("mission","General"), "lenses": data.get("lenses",""),
                            "score_novelty": data.get("score_novelty",0), 
                            "score_evidence": data.get("score_evidence",0),
                            "score_evocativeness": data.get("score_evocativeness",0)
                        })
                        outputs.append({"tool_call_id": tool.id, "output": "displayed"})
                await asyncio.to_thread(client.beta.threads.runs.submit_tool_outputs, thread_id=thread.id, run_id=run.id, tool_outputs=outputs)
            elif status.status == 'completed': return {"signals": acc}
            elif status.status in ['failed', 'expired']: raise HTTPException(500, f"AI Error: {status.last_error}")
            await asyncio.sleep(1)
    except Exception as e: raise HTTPException(500, str(e))
