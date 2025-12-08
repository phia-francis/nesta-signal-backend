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
            print("⚠️ Missing Google Credentials or Sheet ID")
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
    """Returns public config like the Sheet URL."""
    return {"sheet_url": SHEET_URL}

@app.get("/api/saved")
def get_saved_signals():
    """Fetches saved signals from Google Sheets for the Vault UI."""
    try:
        sheet = get_google_sheet()
        if not sheet: return []
        
        # Get all records
        records = sheet.get_all_records()
        return records[::-1] # Newest first
    except Exception as e:
        print(f"Read Error: {e}")
        return [] 

@app.post("/api/save")
def save_signal(signal: SaveSignalRequest):
    """Saves a signal to the Google Sheet."""
    try:
        sheet = get_google_sheet()
        if not sheet:
            raise HTTPException(status_code=500, detail="Could not connect to Google Sheets")
        
        # Row format must match your Sheet headers
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
    return {"status": "ignored", "message": "Please delete directly from Google Sheets"}

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    try:
        print(f"Query: {req.message} | Mode: {req.tech_mode}")
        
        # ---------------------------------------------------------
        # ✅ 1. DEDUPLICATION LOGIC (Check Google Sheets)
        # ---------------------------------------------------------
        existing_titles = []
        try:
            sheet = get_google_sheet()
            if sheet:
                # Fetch Column A (Titles)
                # We limit to the last 100 to keep the prompt size manageable
                titles_col = sheet.col_values(1)
                existing_titles = titles_col[-100:] 
        except Exception as e:
            print(f"Dedup Warning: Could not fetch existing titles. {e}")

        # ---------------------------------------------------------
        # ✅ 2. PROMPT CONSTRUCTION
        # ---------------------------------------------------------
        prompt = req.message
        
        # A. Mode & Constraints
        if req.tech_mode:
            prompt += "\n\nCONSTRAINT: This is a TECHNICAL HORIZON SCAN. Focus ONLY on hard tech (hardware, biotech, materials, code). Ignore policy or social trends."
        
        if req.source_types:
            sources_str = ", ".join(req.source_types)
            prompt += f"\n\nCONSTRAINT: Prioritize findings from these sources: {sources_str}."

        prompt += f"\n\nCONSTRAINT: Time Horizon is '{req.time_filter}'."

        # B. Randomness (Salt)
        # Forces the LLM to traverse a different probability path
        prompt += f"\n\n[System Note: Random Seed {random.randint(1000, 9999)}]"
        
        # C. The Blocklist (The "Novelty" Filter)
        if existing_titles:
            # Clean up the list (remove header 'Title')
            clean_titles = [t for t in existing_titles if t.lower() != "title" and t.strip() != ""]
            
            if clean_titles:
                # Join titles into a string for the prompt
                blocklist_str = ", ".join([f'"{t}"' for t in clean_titles])
                prompt += f"\n\nCRITICAL INSTRUCTION: The user has ALREADY saved the following signals. Do NOT generate cards for these again. You must find *novel* alternatives:\n{blocklist_str}"

        # ---------------------------------------------------------
        # 3. RUN ASSISTANT
        # ---------------------------------------------------------
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
