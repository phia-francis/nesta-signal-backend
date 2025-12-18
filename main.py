import os
import json
import asyncio
import random
import re
import httpx
from datetime import datetime
from urllib.parse import urlparse
from typing import Optional, List, Dict, Any, Set
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel, Field
from openai import OpenAI
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from bs4 import BeautifulSoup
from keywords import MISSION_KEYWORDS, CROSS_CUTTING_KEYWORDS

# --- SETUP ---
load_dotenv()

# API KEYS
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# CONFIG
SHEET_ID = os.getenv("SHEET_ID")
SHEET_URL = os.getenv("SHEET_URL", "#")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS")
GOOGLE_SEARCH_KEY = os.getenv("Google_Search_API_KEY") or os.getenv("GOOGLE_SEARCH_KEY")
GOOGLE_SEARCH_CX = os.getenv("Google_Search_CX") or os.getenv("GOOGLE_SEARCH_CX")

# --- CLIENT INIT ---
client = OpenAI(
    api_key=OPENAI_API_KEY,
    default_headers={"OpenAI-Beta": "assistants=v2"}
)

app = FastAPI()

# ✅ STRONG CORS CONFIGURATION
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
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        g_client = gspread.authorize(creds)
        return g_client.open_by_key(SHEET_ID).sheet1
    except Exception as e:
        print(f"❌ Google Sheets Auth Error: {e}")
        return None

def ensure_sheet_headers(sheet):
    expected_headers = [
        "Title", "Score", "Hook", "URL", "Mission", "Lenses",
        "Score_Evocativeness", "Score_Novelty", "Score_Evidence",
        "User_Rating", "User_Status", "User_Comment", "Shareable", "Feedback", "Source_Date"
    ]
    try:
        existing_headers = sheet.row_values(1)
        if existing_headers != expected_headers:
            sheet.update([expected_headers], 'A1')
    except Exception as e:
        print(f"⚠️ Header Check Failed: {e}")

async def fetch_article_text(url: str) -> str:
    """Scrapes the URL to get the actual content for better hooks/validation."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code >= 400:
                return f"Error: Could not read page (Status {resp.status_code})"
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()
            
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            return text[:2500] + "..."
    except Exception as e:
        return f"Error reading article: {str(e)}"

def get_sheet_records(include_rejected: bool = False) -> List[Dict[str, Any]]:
    sheet = get_google_sheet()
    if not sheet: return []
    ensure_sheet_headers(sheet)
    try:
        rows = sheet.get_all_values()
        if not rows: return []
        headers = rows[0]
        records = []
        for idx, row in enumerate(rows[1:], start=2):
            if all(cell == "" for cell in row): continue
            while len(row) < len(headers): row.append("")
            record = {headers[i]: row[i] for i in range(len(headers))}
            record["_row"] = idx
            status = str(record.get("User_Status", "")).lower()
            if not include_rejected and status == "rejected": continue
            records.append(record)
        return records
    except Exception as e:
        print(f"Read Error: {e}")
        return []

def upsert_signal(signal: Dict[str, Any]) -> None:
    sheet = get_google_sheet()
    if not sheet: return
    ensure_sheet_headers(sheet)
    
    row_data = [
        signal.get("title", ""), 
        signal.get("score", 0),
        signal.get("hook", ""), 
        signal.get("url", ""), 
        signal.get("mission", ""),
        signal.get("lenses", ""), 
        signal.get("score_evocativeness", 0),
        signal.get("score_novelty", 0), 
        signal.get("score_evidence", 0),
        signal.get("user_rating", 3), 
        signal.get("user_status", "Pending"),
        signal.get("user_comment", "") or signal.get("feedback", ""), 
        signal.get("shareable", "Maybe"),
        signal.get("feedback", ""),
        signal.get("source_date", "Recent")
    ]

    try:
        records = get_sheet_records(include_rejected=True)
        match_row = None
        incoming_url = str(signal.get("url", "")).strip().lower()
        
        for rec in records:
            if str(rec.get("URL", "")).strip().lower() == incoming_url:
                match_row = rec.get("_row")
                break
        
        if match_row:
            sheet.update(f"A{match_row}:O{match_row}", [row_data])
        else:
            sheet.append_row(row_data)
    except Exception as e:
        print(f"Upsert Error: {e}")

async def perform_google_search(query, date_restrict="m1", requested_results: int = 8):
    if not GOOGLE_SEARCH_KEY or not GOOGLE_SEARCH_CX: return "System Error: Search Config Missing"
    target_results = max(1, min(20, requested_results))
    print(f"🔍 Searching: '{query}' ({date_restrict})...")
    url = "https://www.googleapis.com/customsearch/v1"
    results = []
    start_index = 1
    async with httpx.AsyncClient() as http_client:
        try:
            while len(results) < target_results:
                params = {
                    "key": GOOGLE_SEARCH_KEY, "cx": GOOGLE_SEARCH_CX,
                    "q": query, "num": 10, "start": start_index, "dateRestrict": date_restrict
                }
                resp = await http_client.get(url, params=params)
                if resp.status_code != 200: break
                items = resp.json().get("items", [])
                if not items: break
                for item in items:
                    results.append(f"Title: {item.get('title')}\nLink: {item.get('link')}\nSnippet: {item.get('snippet', '')}")
                if len(items) < 10: break
                start_index += 10
            return "\n\n".join(results[:target_results])
        except Exception as e: return f"Search Exception: {str(e)}"

# --- ENDPOINTS ---
class ChatRequest(BaseModel):
    message: str
    time_filter: str = "Past Month"
    source_types: List[str] = Field(default_factory=list)
    tech_mode: bool = False

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    run = None
    try:
        # 1. Get Current Date
        today_str = datetime.now().strftime("%Y-%m-%d")
        print(f"Incoming: {req.message} | Date: {today_str}")
        
        # 2. Construct Prompt
        prompt_parts = [
            req.message,
            f"CURRENT DATE: {today_str}",
            "ROLE: You are Nesta's Discovery Hub Lead Foresight Researcher.",
            "PROTOCOL: 1. SEARCH high-friction queries (e.g., 'unregulated', 'banned', 'DIY', 'citizen science', 'stealth startup', 'novel application'). 2. SELECT best candidates. 3. READ candidates (using 'fetch_article_text') to verify they are real/relevant. 4. DISPLAY cards only for verified signals.",
            "SEARCH RULE: Do NOT include specific years (e.g., '2024', '2025') or 'since:' operators in your search queries. The search tool automatically applies the correct time filter based on the user's selection.",
            "TOOL CONTRACT: You MUST call 'fetch_article_text' on a URL before calling 'display_signal_card'. Never display a card based solely on a Google snippet."
        ]
        prompt = "\n\n".join(prompt_parts)
        if req.tech_mode: prompt += "\nCONSTRAINT: Hard Tech / Emerging Tech ONLY."
        
        # Explicit instruction for Gateway to Research
        bias_sources = req.source_types
        if "Gateway to Research" in bias_sources:
            prompt += "\nCONSTRAINT: User selected 'Gateway to Research'. You MUST include searches using 'site:gtr.ukri.org' to find relevant projects."
        
        prompt += f"\nCONSTRAINT: Time Horizon {req.time_filter}. Bias Source Types: {', '.join(bias_sources)}."
        
        run = await asyncio.to_thread(
            client.beta.threads.create_and_run,
            assistant_id=ASSISTANT_ID,
            thread={"messages": [{"role": "user", "content": prompt}]}
        )

        accumulated_signals = []
        seen_urls = set()

        # Polling Loop with Cancellation Support
        while True:
            try:
                run_status = await asyncio.to_thread(client.beta.threads.runs.retrieve, thread_id=run.thread_id, run_id=run.id)
                
                if run_status.status == 'requires_action':
                    tool_calls = run_status.required_action.submit_tool_outputs.tool_calls
                    tool_outputs = []
                    
                    for tool in tool_calls:
                        if tool.function.name == "perform_web_search":
                            args = json.loads(tool.function.arguments)
                            d_map = {"Past Month": "m1", "Past 3 Months": "m3", "Past 6 Months": "m6", "Past Year": "y1"}
                            res = await perform_google_search(args.get("query"), d_map.get(req.time_filter, "m1"))
                            tool_outputs.append({"tool_call_id": tool.id, "output": res})
                        elif tool.function.name == "fetch_article_text":
                            args = json.loads(tool.function.arguments)
                            content = await fetch_article_text(args.get("url"))
                            tool_outputs.append({"tool_call_id": tool.id, "output": content})
                        elif tool.function.name == "display_signal_card":
                            args = json.loads(tool.function.arguments)
                            card = {
                                "title": args.get("title"), "url": args.get("final_url") or args.get("url"),
                                "hook": args.get("hook"), "score": args.get("score"),
                                "mission": args.get("mission", "General"),
                                "lenses": args.get("lenses", ""),
                                "score_novelty": args.get("score_novelty", 0),
                                "score_evidence": args.get("score_evidence", 0),
                                "score_evocativeness": args.get("score_evocativeness", 0),
                                "source_date": args.get("published_date", "Recent"),
                                "ui_type": "signal_card"
                            }
                            if card["url"] and card["url"] not in seen_urls:
                                accumulated_signals.append(card)
                                seen_urls.add(card["url"])
                                # Upsert in thread to prevent blocking cancellation
                                try: await asyncio.to_thread(upsert_signal, card)
                                except: pass
                                tool_outputs.append({"tool_call_id": tool.id, "output": "displayed"})
                            else:
                                tool_outputs.append({"tool_call_id": tool.id, "output": "duplicate_skipped"})

                    await asyncio.to_thread(client.beta.threads.runs.submit_tool_outputs, thread_id=run.thread_id, run_id=run.id, tool_outputs=tool_outputs)

                elif run_status.status == 'completed':
                    if accumulated_signals:
                        return {"ui_type": "signal_list", "items": accumulated_signals}
                    else:
                        msgs = await asyncio.to_thread(client.beta.threads.messages.list, thread_id=run.thread_id)
                        return {"ui_type": "text", "content": msgs.data[0].content[0].text.value}
                
                elif run_status.status in ['failed', 'expired', 'cancelled']:
                    return {"ui_type": "text", "content": f"System Error: {run_status.last_error}"}
                
                await asyncio.sleep(1)

            except asyncio.CancelledError:
                print(f"🛑 Scan cancelled by user. Terminating Run {run.id}...")
                try:
                    await asyncio.to_thread(client.beta.threads.runs.cancel, thread_id=run.thread_id, run_id=run.id)
                except Exception as e:
                    print(f"Error cancelling run: {e}")
                raise # Re-raise to allow FastAPI to close the connection properly

    except Exception as e:
        print(f"Server Error: {e}")
        # Only check for cancellation if 'run' was created
        if isinstance(e, asyncio.CancelledError) and run:
            try:
                await asyncio.to_thread(client.beta.threads.runs.cancel, thread_id=run.thread_id, run_id=run.id)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/saved")
def get_saved(): return get_sheet_records()

@app.post("/api/update")
def update_sig(req: Dict[str, Any]): 
    try:
        upsert_signal(req)
        return {"status": "updated"}
    except Exception as e:
        print(f"Update Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- STATIC FILE SERVING ---
@app.get("/")
def serve_home():
    try:
        with open("index.html", "r") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except:
        return HTMLResponse(content="<h1>Backend Running</h1>", status_code=200)

@app.get("/Zosia-Display.woff2")
def serve_font1(): return FileResponse("Zosia-Display.woff2")

@app.get("/Averta-Regular.otf")
def serve_font2(): return FileResponse("Averta-Regular.otf")

@app.get("/Averta-Semibold.otf")
def serve_font3(): return FileResponse("Averta-Semibold.otf")
