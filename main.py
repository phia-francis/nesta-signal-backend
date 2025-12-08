import os
import json
import asyncio
import random
import httpx # ✅ NEW: For Google Search requests
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
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
SHEET_ID = os.getenv("SHEET_ID")
SHEET_URL = os.getenv("SHEET_URL", "#")
# ✅ NEW: Search Credentials
GOOGLE_SEARCH_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGLE_SEARCH_CX = os.getenv("GOOGLE_SEARCH_CX")

# --- GOOGLE AUTH HELPER (SHEETS) ---
def get_google_sheet():
    try:
        if not os.getenv("GOOGLE_CREDENTIALS") or not SHEET_ID:
            return None
        json_creds = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(json_creds, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(SHEET_ID).sheet1
    except Exception as e:
        print(f"Google Auth Error: {e}")
        return None

# --- NEW: GOOGLE SEARCH HELPER (DEBUG VERSION) ---
async def perform_google_search(query):
    """Performs a real Google Search to validate signals."""
    if not GOOGLE_SEARCH_KEY or not GOOGLE_SEARCH_CX:
        print("❌ CONFIG ERROR: Missing Google Search Keys")
        return "System Error: Search is not configured. Proceed with internal knowledge but flag as unverified."
    
    print(f"🔍 Searching Google for: '{query}'...")
    
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_SEARCH_KEY,
        "cx": GOOGLE_SEARCH_CX,
        "q": query,
        "num": 3
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params)
            
            # Debug: Print error if API fails
            if resp.status_code != 200:
                print(f"❌ Google API Error: {resp.text}")
                return f"Search Failed: {resp.status_code}. Proceed with best estimate."

            data = resp.json()
            
            if "items" not in data:
                print("⚠️ No results found.")
                return "No search results found. Use internal knowledge."
            
            # Format results
            results = []
            for item in data["items"]:
                results.append(f"Title: {item['title']}\nLink: {item['link']}\nSnippet: {item.get('snippet', '')}")
            
            output = "\n\n".join(results)
            print("✅ Search Successful. Results found.")
            return output

        except Exception as e:
            print(f"❌ Exception during search: {e}")
            return f"Search Exception: {str(e)}"

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
    return {"sheet_url": SHEET_URL}

@app.get("/api/saved")
def get_saved_signals():
    try:
        sheet = get_google_sheet()
        if not sheet: return []
        records = sheet.get_all_records()
        return records[::-1]
    except Exception: return [] 

@app.post("/api/save")
def save_signal(signal: SaveSignalRequest):
    try:
        sheet = get_google_sheet()
        if not sheet: raise HTTPException(status_code=500, detail="No Sheet Connection")
        row = [
            signal.title, signal.score, signal.archetype, signal.hook, signal.url,
            signal.mission, signal.lenses, signal.score_evocativeness,
            signal.score_novelty, signal.score_evidence
        ]
        sheet.append_row(row)
        return {"status": "success"}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/saved/{signal_id}")
def delete_signal(signal_id: int):
    return {"status": "ignored", "message": "Delete from Google Sheets directly"}

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    try:
        print(f"Query: {req.message}")
        
        # 1. Deduping
        existing_titles = []
        try:
            sheet = get_google_sheet()
            if sheet: existing_titles = sheet.col_values(1)[-50:]
        except Exception: pass

        # 2. Prompt Construction
        prompt = req.message
        if req.tech_mode: prompt += "\n\nCONSTRAINT: TECHNICAL HORIZON SCAN ONLY (Hardware, Biotech, Code)."
        if req.source_types: prompt += f"\n\nCONSTRAINT: Prioritize sources: {', '.join(req.source_types)}."
        prompt += f"\n\nCONSTRAINT: Time Horizon '{req.time_filter}'."
        prompt += f"\n\n[System Note: Random Seed {random.randint(1000, 9999)}]"
        
        clean_titles = [t for t in existing_titles if t.lower() != "title"]
        if clean_titles: prompt += f"\n\nBLOCKLIST: Do NOT return these: {', '.join(clean_titles)}"

        # 3. Run Assistant
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
                    # ✅ NEW: Handle Search Tool
                    if tool.function.name == "perform_web_search":
                        args = json.loads(tool.function.arguments)
                        search_query = args.get("query")
                        print(f"🔎 Searching Google for: {search_query}")
                        
                        search_result = await perform_google_search(search_query)
                        
                        tool_outputs.append({
                            "tool_call_id": tool.id,
                            "output": search_result
                        })

                    # Handle Card Display
                    elif tool.function.name == "display_signal_card":
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
                
                # Only return to UI if we actually found cards.
                # If we only performed a search, the loop continues so the AI can read the results.
                if signals_found:
                    return {"ui_type": "signal_list", "items": signals_found}
                        
            if run_status.status == 'completed':
                messages = await asyncio.to_thread(
                    client.beta.threads.messages.list, thread_id=run.thread_id
                )
                if messages.data:
                    return {"ui_type": "text", "content": messages.data[0].content[0].text.value}
                return {"ui_type": "text", "content": "Scan complete."}
            
            if run_status.status in ['failed', 'cancelled', 'expired']:
                return {"ui_type": "text", "content": "I encountered an error."}

            await asyncio.sleep(1)

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
