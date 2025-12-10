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
from google.oauth2.service_account import Credentials

# --- SETUP ---
load_dotenv()

# API KEYS
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# GOOGLE CONFIG
SHEET_ID = os.getenv("SHEET_ID")
SHEET_URL = os.getenv("SHEET_URL", "#")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS")
GOOGLE_SEARCH_KEY = os.getenv("Google_Search_API_KEY") 
GOOGLE_SEARCH_CX = os.getenv("Google_Search_CX")

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
    """Fetches high-quality examples (Accepted or 4+ Stars)."""
    try:
        sheet = get_google_sheet()
        if not sheet: return ""
        
        records = sheet.get_all_records()
        if not records: return ""
        
        good_signals = []
        for r in records:
            try:
                status = str(r.get('User_Status', '')).lower()
                raw_rating = r.get('User_Rating', 0)
                rating = int(raw_rating) if raw_rating != "" else 0
                
                if status == "accepted" or rating >= 4:
                    good_signals.append(r)
            except ValueError:
                continue 
        
        if not good_signals: return ""

        examples = random.sample(good_signals, k=min(3, len(good_signals)))
        
        example_str = "### USER'S GOLD STANDARD EXAMPLES (EMULATE THESE):\n"
        for i, ex in enumerate(examples, 1):
            title = ex.get('Title', 'Untitled')
            hook = ex.get('Hook', '')
            comment = ex.get('User_Comment', '')
            
            example_str += f"{i}. Title: {title}\n   Hook: {hook}\n"
            if comment: example_str += f"   User Note: {comment}\n"
            example_str += "\n"
            
        return example_str

    except Exception as e:
        print(f"Learning Error: {e}")
        return ""

def get_date_restrict(filter_text):
    """Maps UI 'Time Horizon' text to Google API 'dateRestrict' values."""
    mapping = {
        "Past Month": "m1",
        "Past 3 Months": "m3",
        "Past 6 Months": "m6",
        "Past Year": "y1"
    }
    # Default to 1 year if unknown
    return mapping.get(filter_text, "y1")

def infer_requested_signal_count(message: str) -> Optional[int]:
    """Best-effort parse of how many signals the user asked for."""
    try:
        match = re.search(r"\b(\d{1,2})\s*(?:new\s+)?(?:signals?|findings?|examples?)", message, re.IGNORECASE)
        return int(match.group(1)) if match else None
    except ValueError:
        return None


def determine_search_target_count(requested_signal_count: Optional[int]) -> int:
    """Scale search result volume with requested signal count (bounded to protect API usage)."""
    if requested_signal_count is None:
        return 8
    return max(5, min(20, requested_signal_count * 2))


async def perform_google_search(query, date_restrict="y1", requested_results: int = 8):
    """
    Performs a real web search using Google Custom Search API.
    ✅ NOW ENFORCES DATE RESTRICTION.
    """
    if not GOOGLE_SEARCH_KEY or not GOOGLE_SEARCH_CX:
        print("❌ CONFIG ERROR: Missing Google Search Keys")
        return "System Error: Search is not configured."

    target_results = max(1, min(20, requested_results))
    print(f"🔍 Searching Google for: '{query}' (Filter: {date_restrict}, Target Results: {target_results})...")

    url = "https://www.googleapis.com/customsearch/v1"
    results = []
    start_index = 1

    async with httpx.AsyncClient() as http_client:
        try:
            while len(results) < target_results:
                remaining = target_results - len(results)
                page_size = min(10, remaining)  # Google API caps 'num' at 10
                params = {
                    "key": GOOGLE_SEARCH_KEY,
                    "cx": GOOGLE_SEARCH_CX,
                    "q": query,
                    "num": page_size,
                    "start": start_index,
                    "dateRestrict": date_restrict  # ✅ Forces results to be recent
                }

                resp = await http_client.get(url, params=params)

                if resp.status_code != 200:
                    print(f"❌ Google API Error: {resp.text}")
                    return f"Search Failed: {resp.status_code}."

                data = resp.json()

                items = data.get("items", [])
                if not items:
                    break

                for item in items:
                    # Include snippet and link so AI can verify date context
                    results.append(f"Title: {item.get('title')}\nLink: {item.get('link')}\nSnippet: {item.get('snippet', '')}")

                # Avoid infinite loops if Google returns fewer than requested
                if len(items) < page_size:
                    break

                start_index += page_size

            if not results:
                return "No search results found. Try a different query."

            return "\n\n".join(results[:target_results])

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
    user_rating: Optional[int] = 0
    user_status: Optional[str] = "Pending"
    user_comment: Optional[str] = ""

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
    except Exception as e:
        print(f"Read Error: {e}")
        return [] 

@app.post("/api/save")
def save_signal(signal: SaveSignalRequest):
    try:
        sheet = get_google_sheet()
        if not sheet:
            raise HTTPException(status_code=500, detail="Could not connect to Google Sheets")
        
        row = [
            signal.title, signal.score, signal.archetype, signal.hook, signal.url,
            signal.mission, signal.lenses, signal.score_evocativeness,
            signal.score_novelty, signal.score_evidence,
            signal.user_rating, signal.user_status, signal.user_comment
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
        print(f"Incoming Query: {req.message} | Filters: {req.time_filter}, TechMode: {req.tech_mode}")

        # 1. FETCH CONTEXT
        existing_titles = []
        learning_prompt = ""
        requested_signal_count = infer_requested_signal_count(req.message)
        search_result_target = determine_search_target_count(requested_signal_count)

        try:
            sheet = get_google_sheet()
            if sheet:
                col_values = sheet.col_values(1)
                existing_titles = col_values[-50:] 
                learning_prompt = get_learning_examples()
        except Exception as e:
            print(f"Context Fetch Warning: {e}")

        # 2. PROMPT CONSTRUCTION
        prompt = req.message
        
        # ✅ NEW: STRICT ANTI-HALLUCINATION INJECTION
        prompt += """
        
        SYSTEM PROTOCOL:
        1. You are in 'Research Mode'. You have NO internal memory of URLs.
        2. You MUST use 'perform_web_search' to find real signals.
        3. COPY THE URL EXACTLY from the search results. Do not type it out from memory.
        4. If the search returns no valid links, return text saying 'No verified signals found' instead of hallucinating a fake card.
        """
        
        if learning_prompt:
            prompt += f"\n\n{learning_prompt}"
            prompt += "\nINSTRUCTION: Analyze the 'User Notes' and style of the examples above. Adjust your search strategy to match this taste profile."

        prompt += "\n\nSYSTEM INSTRUCTION: You currently have 0 verified signals. You MUST use the 'perform_web_search' tool to find real articles before generating any cards. Do not generate cards from memory."

        if req.tech_mode:
            prompt += "\n\nCONSTRAINT: This is a TECHNICAL HORIZON SCAN. Search ONLY for Hard Tech (Hardware, Biotech, Materials, Code)."
        
        if req.source_types:
            sources_str = ", ".join(req.source_types)
            prompt += f"\n\nCONSTRAINT: Prioritize findings from these source types: {sources_str}."

        prompt += f"\n\nCONSTRAINT: Time Horizon is '{req.time_filter}'. Ensure signals are recent."
        prompt += f"\n\n[System Note: Random Seed {random.randint(1000, 9999)}]"
        
        clean_titles = [t for t in existing_titles if t.lower() != "title" and t.strip() != ""]
        if clean_titles:
            blocklist_str = ", ".join([f'"{t}"' for t in clean_titles])
            prompt += f"\n\nIMPORTANT: Do NOT return these titles (user already has them): {blocklist_str}"

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
                    if tool.function.name == "perform_web_search":
                        args = json.loads(tool.function.arguments)
                        search_query = args.get("query")

                        # ✅ PASS TIME FILTER TO SEARCH FUNCTION
                        date_code = get_date_restrict(req.time_filter)
                        search_result = await perform_google_search(
                            search_query,
                            date_code,
                            requested_results=search_result_target
                        )
                        
                        tool_outputs.append({
                            "tool_call_id": tool.id,
                            "output": search_result
                        })

                    elif tool.function.name == "display_signal_card":
                        args = json.loads(tool.function.arguments)
                        processed_card = craft_widget_response(args)
                        accumulated_signals.append(processed_card)
                        tool_outputs.append({
                            "tool_call_id": tool.id,
                            "output": json.dumps({"status": "displayed"})
                        })

                await asyncio.to_thread(
                    client.beta.threads.runs.submit_tool_outputs,
                    thread_id=run.thread_id,
                    run_id=run.id,
                    tool_outputs=tool_outputs
                )
                
            if run_status.status == 'completed':
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
            
            if run_status.status == 'failed':
                # ✅ NEW: Fetch the actual error reason from OpenAI
                error_message = run_status.last_error.message if run_status.last_error else "Unknown error"
                error_code = run_status.last_error.code if run_status.last_error else "unknown_code"
                
                print(f"❌ OPENAI RUN FAILED: {error_code} - {error_message}")
                
                return {
                    "ui_type": "text", 
                    "content": f"I encountered an error. Debug Info: {error_message}"
                }
            
            if run_status.status in ['cancelled', 'expired']:
                print(f"Run Status: {run_status.status}")
                return {"ui_type": "text", "content": "The request timed out or was cancelled."}

            await asyncio.sleep(1)

    except Exception as e:
        print(f"Critical Backend Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
