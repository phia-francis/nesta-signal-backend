import os
import json
import asyncio
import random
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

# --- SETUP ---
load_dotenv()
ASSISTANT_ID = os.getenv("ASSISTANT_ID", "asst_6AnFZkW7f6Jhns774D9GNWXr")
SHEET_ID = os.getenv("SHEET_ID")
SHEET_URL = os.getenv("SHEET_URL", "#")

# --- GOOGLE AUTH HELPER ---
def get_google_sheet():
    """Authenticates with Google and returns the Sheet object."""
    try:
        if not os.getenv("GOOGLE_CREDENTIALS") or not SHEET_ID:
            print("⚠️ Missing Google Credentials or Sheet ID in Environment Variables.")
            return None
            
        json_creds = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(json_creds, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(SHEET_ID).sheet1
    except Exception as e:
        print(f"Google Auth Error: {e}")
        return None

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

# --- DATA MODELS ---
class ChatRequest(BaseModel):
    message: str
    time_filter: str = "Past Year"
    source_types: List[str] = []
    tech_mode: bool = False

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

@app.get("/api/config")
def get_config():
    """Returns public config like the Sheet URL for the frontend."""
    return {"sheet_url": SHEET_URL}

@app.get("/api/saved")
def get_saved_signals():
    """Fetches saved signals from Google Sheets."""
    try:
        sheet = get_google_sheet()
        if not sheet:
            # Fallback for dev/testing if no sheet connected
            return []
        
        # Get all records as list of dicts
        records = sheet.get_all_records()
        
        # Reverse to show newest first
        return records[::-1]
    except Exception as e:
        print(f"Read Error: {e}")
        return [] 

@app.post("/api/save")
def save_signal(signal: SaveSignalRequest):
    """Saves a single signal to Google Sheets."""
    try:
        sheet = get_google_sheet()
        if not sheet:
            raise HTTPException(status_code=500, detail="Could not connect to Google Sheets")
        
        # Row format: Title, Score, Archetype, Hook, URL, Mission, Lenses, Evo, Nov, Evi
        row = [
            signal.title,
            signal.score,
            signal.archetype,
            signal.hook,
            signal.url,
            signal.mission,
            signal.lenses,
            signal.score_evocativeness,
            signal.score_novelty,
            signal.score_evidence
        ]
        
        sheet.append_row(row)
        return {"status": "success"}
    except Exception as e:
        print(f"Save Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/saved/{signal_id}")
def delete_signal(signal_id: int):
    # Deleting via index in Sheets is risky. We rely on the Sheet for management.
    return {"status": "ignored", "message": "Please delete directly from Google Sheets"}

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    try:
        print(f"Query: {req.message} | Filters: Time={req.time_filter}, Tech={req.tech_mode}, Sources={req.source_types}")
        
        # 1. Deduping (Fetch last 50 titles from Sheet)
        existing_titles = []
        try:
            sheet = get_google_sheet()
            if sheet:
                # Fetch only column A (Titles) to save bandwidth
                titles_col = sheet.col_values(1)
                existing_titles = titles_col[-50:] 
        except Exception: pass

        # 2. PROMPT CONSTRUCTION
        prompt = req.message
        
        if req.tech_mode:
            prompt += "\n\nCONSTRAINT: This is a TECHNICAL HORIZON SCAN. Focus ONLY on emerging hardware, software, materials, or biotech. Ignore purely cultural trends."

        if req.source_types:
            sources_str = ", ".join(req.source_types)
            prompt += f"\n\nCONSTRAINT: Prioritize findings from these specific source types: {sources_str}."

        prompt += f"\n\nCONSTRAINT: Time Horizon is '{req.time_filter}'. Ensure signals are recent."

        prompt += f"\n\n[System Note: Random Seed {random.randint(1000, 9999)}]"
        
        if existing_titles:
            # Filter out the header "Title" if present
            clean_titles = [t for t in existing_titles if t.lower() != "title"]
            if clean_titles:
                blocklist_str = ", ".join([f'"{t}"' for t in clean_titles])
                prompt += f"\n\nIMPORTANT: Do NOT return these titles (user has already saved them): {blocklist_str}"

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
                        
                        # Note: If you want auto-save, uncomment the line below:
                        # save_signal(SaveSignalRequest(**processed_card))
                        
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
                # Handle case where AI talks but calls no tools
                if messages.data:
                    text = messages.data[0].content[0].text.value
                    return {"ui_type": "text", "content": text}
                else:
                    return {"ui_type": "text", "content": "Scan complete, but no signals generated."}
            
            if run_status.status in ['failed', 'cancelled', 'expired']:
                return {"ui_type": "text", "content": "I encountered an error processing that signal."}

            await asyncio.sleep(1)

    except Exception as e:
        print(f"Critical Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
