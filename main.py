import os
import json
import asyncio
import random
import httpx
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

# API KEYS
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# GOOGLE SHEETS CONFIG
SHEET_ID = os.getenv("SHEET_ID")
SHEET_URL = os.getenv("SHEET_URL", "#")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS")

# GOOGLE SEARCH CONFIG
GOOGLE_SEARCH_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGLE_SEARCH_CX = os.getenv("GOOGLE_SEARCH_CX")

# --- CLIENT INIT ---
client = OpenAI(
    api_key=OPENAI_API_KEY,
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

# --- HELPERS ---

def get_google_sheet():
    """Authenticates and returns the Google Sheet object."""
    try:
        if not GOOGLE_CREDENTIALS_JSON or not SHEET_ID:
            print("⚠️ Google Sheets credentials missing.")
            return None
            
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        g_client = gspread.authorize(creds)
        return g_client.open_by_key(SHEET_ID).sheet1
    except Exception as e:
        print(f"❌ Google Sheets Auth Error: {e}")
        return None

def get_learning_examples():
    """
    Fetches high-quality examples (Accepted or 4+ Stars) from the Sheet
    to train the AI on what 'Good' looks like via In-Context Learning.
    """
    try:
        sheet = get_google_sheet()
        if not sheet: return ""
        
        records = sheet.get_all_records()
        if not records: return ""
        
        # Filter for "Good" signals (Accepted OR Rating >= 4)
        good_signals = [
            r for r in records 
            if str(r.get('Status', r.get('user_status', ''))).lower() == "accepted" 
            or int(r.get('User Rating', r.get('user_rating', 0)) or 0) >= 4
        ]
        
        if not good_signals:
            return ""

        # Pick 3 random examples to keep prompt fresh
        examples = random.sample(good_signals, k=min(3, len(good_signals)))
        
        example_str = "### USER'S GOLD STANDARD EXAMPLES (EMULATE THESE):\n"
        for i, ex in enumerate(examples, 1):
            title = ex.get('Title') or ex.get('title')
            hook = ex.get('Hook') or ex.get('hook')
            comment = ex.get('Comment') or ex.get('user_comment') or ""
            
            example_str += f"{i}. Title: {title}\n   Hook: {hook}\n"
            if comment:
                example_str += f"   User Note: {comment}\n"
            example_str += "\n"
            
        return example_str

    except Exception as e:
        print(f"Learning Error: {e}")
        return ""

async def perform_google_search(query):
    """Performs a real web search using Google Custom Search API."""
    if not GOOGLE_SEARCH_KEY or not GOOGLE_SEARCH_CX:
        print("❌ CONFIG ERROR: Missing Google Search Keys")
        return "System Error: Search is not configured. Proceed with internal knowledge but flag as unverified."
    
    print(f"🔍 Searching Google for: '{query}'...")
    
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_SEARCH_KEY,
        "cx": GOOGLE_SEARCH_CX,
        "q": query,
        "num": 3 # Fetch top 3 results to save quota
    }
    
    async with httpx.AsyncClient() as http_client:
        try:
            resp = await http_client.get(url, params=params)
            
            # Handle non-200 responses without crashing
            if resp.status_code != 200:
                print(f"❌ Google API Error: {resp.text}")
                return f"Search Failed: {resp.status_code}. Proceed with best estimate."

            data = resp.json()
            
            if "items" not in data:
                print("⚠️ No results found.")
                return "No search results found. Try a different query."
            
            # Format results for the AI
            results = []
            for item in data["items"]:
                results.append(f"Title: {item.get('title')}\nLink: {item.get('link')}\nSnippet: {item.get('snippet', '')}")
            
            output = "\n\n".join(results)
            print("✅ Search Successful.")
            return output

        except Exception as e:
            print(f"❌ Exception during search: {e}")
            return f"Search Exception: {str(e)}"

def craft_widget_response(tool_args):
    """Standardizes the card data for the frontend."""
    url = tool_args.get("sourceURL") or tool_args.get("url")
    if not url:
        query = tool_args.get("title", "").replace(" ", "+")
        url = f"https://www.google.com/search?q={query}"
    
    tool_args["final_url"] = url
    tool_args["ui_type"] = "signal_card"
    return tool_args

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
    # Feedback Fields
    user_rating: Optional[int] = 0
    user_status: Optional[str] = "Pending"
    user_comment: Optional[str] = ""

# --- API ENDPOINTS ---

@app.get("/api/config")
def get_config():
    """Returns public config like the Sheet URL."""
    return {"sheet_url": SHEET_URL}

@app.get("/api/saved")
def get_saved_signals():
    """Fetches saved signals from Google Sheets."""
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
    """Saves a signal to Google Sheets."""
    try:
        sheet = get_google_sheet()
        if not sheet:
            raise HTTPException(status_code=500, detail="Could not connect to Google Sheets")
        
        # Row format must match your Sheet Headers EXACTLY
        # Title, Score, Archetype, Hook, URL, Mission, Lenses, Evo, Nov, Evi, Rating, Status, Comment
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
            signal.score_evidence,
            signal.user_rating,
            signal.user_status,
            signal.user_comment
        ]
        
        sheet.append_row(row)
        return {"status": "success"}
    except Exception as e:
        print(f"Save Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/saved/{signal_id}")
def delete_signal(signal_id: int):
    # We do not delete by index via API to prevent data corruption.
    return {"status": "ignored", "message": "Please delete directly from Google Sheets"}

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    try:
        print(f"Incoming Query: {req.message} | Filters: {req.time_filter}, TechMode: {req.tech_mode}")
        
        # 1. FETCH CONTEXT (Dedup + Learning)
        existing_titles = []
        learning_prompt = ""
        
        try:
            sheet = get_google_sheet()
            if sheet:
                col_values = sheet.col_values(1)
                existing_titles = col_values[-50:] # Last 50 titles
                learning_prompt = get_learning_examples()
        except Exception as e:
            print(f"Context Fetch Warning: {e}")

        # 2. PROMPT CONSTRUCTION
        prompt = req.message
        
        # A. Inject Learning Data
        if learning_prompt:
            prompt += f"\n\n{learning_prompt}"
            prompt += "\nINSTRUCTION: Analyze the 'User Notes' and style of the examples above. Adjust your search strategy to match this taste profile."

        # B. Inject "Search First" Behavior
        prompt += "\n\nSYSTEM INSTRUCTION: You currently have 0 verified signals. You MUST use the 'perform_web_search' tool to find real articles before generating any cards. Do not generate cards from memory."

        # C. Apply User Filters
        if req.tech_mode:
            prompt += "\n\nCONSTRAINT: This is a TECHNICAL HORIZON SCAN. Search ONLY for Hard Tech (Hardware, Biotech, Materials, Code). Ignore policy/social trends."
        
        if req.source_types:
            sources_str = ", ".join(req.source_types)
            prompt += f"\n\nCONSTRAINT: Prioritize findings from these source types: {sources_str}."

        prompt += f"\n\nCONSTRAINT: Time Horizon is '{req.time_filter}'. Ensure signals are recent."
        
        # D. Salt & Blocklist
        prompt += f"\n\n[System Note: Random Seed {random.randint(1000, 9999)}]"
        
        clean_titles = [t for t in existing_titles if t.lower() != "title" and t.strip() != ""]
        if clean_titles:
            blocklist_str = ", ".join([f'"{t}"' for t in clean_titles])
            prompt += f"\n\nIMPORTANT: Do NOT return these titles (user already has them): {blocklist_str}"

        # E. Count Enforcement
        prompt += "\n\nCRITICAL INSTRUCTION: If the user asked for a specific number of signals (e.g. 'Find 5'), you MUST perform enough searches to find exactly that many verified examples. Do not stop early."

        # 3. RUN ASSISTANT
        run = await asyncio.to_thread(
            client.beta.threads.create_and_run,
            assistant_id=ASSISTANT_ID,
            thread={"messages": [{"role": "user", "content": prompt}]}
        )

        accumulated_signals = []

        while True:
            run_status = await asyncio.to_thread(
                client.beta.threads.runs.retrieve, thread_id=run.thread_id, run_id=run.id
            )

            if run_status.status == 'requires_action':
                tool_calls = run_status.required_action.submit_tool_outputs.tool_calls
                tool_outputs = []

                for tool in tool_calls:
                    # Tool A: Search
                    if tool.function.name == "perform_web_search":
                        args = json.loads(tool.function.arguments)
                        search_query = args.get("query")
                        
                        search_result = await perform_google_search(search_query)
                        
                        tool_outputs.append({
                            "tool_call_id": tool.id,
                            "output": search_result
                        })

                    # Tool B: Display Card
                    elif tool.function.name == "display_signal_card":
                        args = json.loads(tool.function.arguments)
                        processed_card = craft_widget_response(args)
                        
                        # Store signal, do NOT return yet (wait for full batch)
                        accumulated_signals.append(processed_card)
                        
                        tool_outputs.append({
                            "tool_call_id": tool.id,
                            "output": json.dumps({"status": "displayed"})
                        })

                # Submit all tool outputs back to AI
                if tool_outputs:
                    await asyncio.to_thread(
                        client.beta.threads.runs.submit_tool_outputs,
                        thread_id=run.thread_id,
                        run_id=run.id,
                        tool_outputs=tool_outputs
                    )
                
                # Loop continues...
                        
            if run_status.status == 'completed':
                # ✅ RETURN EVERYTHING AT THE END
                if accumulated_signals:
                    return {"ui_type": "signal_list", "items": accumulated_signals}
                
                messages = await asyncio.to_thread(
                    client.beta.threads.messages.list, thread_id=run.thread_id
                )
                if messages.data:
                    text = messages.data[0].content[0].text.value
                    return {"ui_type": "text", "content": text}
                else:
                    return {"ui_type": "text", "content": "Scan complete."}
            
            if run_status.status in ['failed', 'cancelled', 'expired']:
                print(f"Run Status: {run_status.status}")
                return {"ui_type": "text", "content": "I encountered an error processing that signal."}

            await asyncio.sleep(1)

    except Exception as e:
        print(f"Critical Backend Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
