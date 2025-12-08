import os
import json
import sqlite3
import asyncio
import random
from datetime import datetime, timedelta
from contextlib import closing
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

# --- SETUP ---
load_dotenv()
ASSISTANT_ID = os.getenv("ASSISTANT_ID", "asst_6AnFZkW7f6Jhns774D9GNWXr")

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    default_headers={"OpenAI-Beta": "assistants=v2"}
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DATABASE SETUP ---
DB_FILE = "signals.db"

def init_db():
    with closing(sqlite3.connect(DB_FILE)) as conn:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS saved_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    score INTEGER,
                    archetype TEXT,
                    hook TEXT,
                    url TEXT,
                    mission TEXT,
                    lenses TEXT,
                    score_evocativeness INTEGER DEFAULT 0,
                    score_novelty INTEGER DEFAULT 0,
                    score_evidence INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Auto-migration logic (same as before)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(saved_signals)")
            columns = [info[1] for info in cursor.fetchall()]
            new_cols = {
                "mission": "TEXT", "lenses": "TEXT",
                "score_evocativeness": "INTEGER DEFAULT 0",
                "score_novelty": "INTEGER DEFAULT 0",
                "score_evidence": "INTEGER DEFAULT 0"
            }
            for col, dtype in new_cols.items():
                if col not in columns:
                    conn.execute(f"ALTER TABLE saved_signals ADD COLUMN {col} {dtype}")
init_db()

# --- DATA MODELS ---
class ChatRequest(BaseModel):
    message: str
    # ✅ NEW FILTER FIELDS
    time_filter: str = "Past Year"     # e.g. "Past Month", "Past Year"
    source_types: List[str] = []       # e.g. ["Academia", "VC Blogs"]
    tech_mode: bool = False            # If True, focus strictly on technology

class SaveSignalRequest(BaseModel):
    title: str
    score: int
    archetype: str
    hook: str
    url: str
    mission: Optional[str] = ""
    lenses: Optional[str] = ""
    score_evocativeness: Optional[int] = 0
    score_novelty: Optional[int] = 0
    score_evidence: Optional[int] = 0

# --- HELPER ---
def craft_widget_response(tool_args):
    url = tool_args.get("sourceURL") or tool_args.get("url")
    if not url:
        query = tool_args.get("title", "").replace(" ", "+")
        url = f"https://www.google.com/search?q={query}"
    
    tool_args["final_url"] = url
    tool_args["ui_type"] = "signal_card"
    return tool_args

# --- ENDPOINTS ---

@app.get("/api/saved")
def get_saved_signals():
    try:
        with closing(sqlite3.connect(DB_FILE)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM saved_signals ORDER BY id DESC")
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/save")
def save_signal(signal: SaveSignalRequest):
    try:
        with closing(sqlite3.connect(DB_FILE)) as conn:
            with conn:
                conn.execute(
                    """INSERT INTO saved_signals 
                       (title, score, archetype, hook, url, mission, lenses, 
                        score_evocativeness, score_novelty, score_evidence) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (signal.title, signal.score, signal.archetype, signal.hook, signal.url, 
                     signal.mission, signal.lenses, 
                     signal.score_evocativeness, signal.score_novelty, signal.score_evidence)
                )
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/saved/{signal_id}")
def delete_signal(signal_id: int):
    try:
        with closing(sqlite3.connect(DB_FILE)) as conn:
            with conn:
                conn.execute("DELETE FROM saved_signals WHERE id = ?", (signal_id,))
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    try:
        print(f"User Query: {req.message} | Filters: {req.time_filter}, {req.source_types}, TechMode: {req.tech_mode}")
        
        # 1. Deduping
        existing_titles = []
        try:
            with closing(sqlite3.connect(DB_FILE)) as conn:
                cursor = conn.execute("SELECT title FROM saved_signals ORDER BY id DESC LIMIT 50")
                existing_titles = [row[0] for row in cursor.fetchall()]
        except Exception: pass

        # 2. CONSTRUCT SOPHISTICATED PROMPT
        prompt = req.message
        
        # A. Tech Mode Injection
        if req.tech_mode:
            prompt += "\n\nCONSTRAINT: This is a TECHNICAL HORIZON SCAN. Ignore social trends, policy ideas, or cultural shifts. Focus ONLY on emerging hardware, software, materials, or biotech breakthroughs."

        # B. Source Filtering
        if req.source_types:
            sources_str = ", ".join(req.source_types)
            prompt += f"\n\nCONSTRAINT: Prioritize findings from these specific source types: {sources_str}. Do not use generic news sites if possible."

        # C. Time Filtering
        today = datetime.now().strftime("%B %Y")
        prompt += f"\n\nCONSTRAINT: Time Horizon is '{req.time_filter}'. Today is {today}. Ensure the signals are active or published within this window."

        # D. Blocklist & Salt
        prompt += f"\n\n[System Note: Random Seed {random.randint(1000, 9999)}]"
        if existing_titles:
            blocklist_str = ", ".join([f'"{t}"' for t in existing_titles])
            prompt += f"\n\nIMPORTANT: Do NOT return these titles: {blocklist_str}"

        # 3. RUN ASSISTANT
        run = await asyncio.to_thread(
            client.beta.threads.create_and_run,
            assistant_id=ASSISTANT_ID,
            thread={"messages": [{"role": "user", "content": prompt}]}
        )

        while True:
            run_status = await asyncio.to_thread(
                client.beta.threads.runs.retrieve, thread_id=run.thread_id, run_id=run.id
            )

            if run_status.status == 'requires_action':
                tool_calls = run_status.required_action.submit_tool_outputs.tool_calls
                signals_found = []
                tool_outputs = []

                for tool in tool_calls:
                    if tool.function.name == "display_signal_card":
                        args = json.loads(tool.function.arguments)
                        processed_card = craft_widget_response(args)
                        signals_found.append(processed_card)
                        tool_outputs.append({
                            "tool_call_id": tool.id,
                            "output": json.dumps({"status": "displayed"})
                        })

                if tool_outputs:
                    await asyncio.to_thread(
                        client.beta.threads.runs.submit_tool_outputs,
                        thread_id=run.thread_id,
                        run_id=run.id,
                        tool_outputs=tool_outputs
                    )
                
                if signals_found:
                    return {"ui_type": "signal_list", "items": signals_found}
                        
            if run_status.status == 'completed':
                messages = await asyncio.to_thread(
                    client.beta.threads.messages.list, thread_id=run.thread_id
                )
                text = messages.data[0].content[0].text.value
                return {"ui_type": "text", "content": text}
            
            if run_status.status in ['failed', 'cancelled', 'expired']:
                return {"ui_type": "text", "content": "I encountered an error processing that signal."}

            await asyncio.sleep(1)

    except Exception as e:
        print(f"Critical Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
