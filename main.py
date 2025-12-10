import os
import json
import asyncio
import random
import re
import httpx
from typing import Optional, List, Dict, Any, Set
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from keywords import MISSION_KEYWORDS, CROSS_CUTTING_KEYWORDS

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


def ensure_sheet_headers(sheet):
    """Guarantee that the sheet has the expected header row."""
    expected_headers = [
        "Title", "Score", "Archetype", "Hook", "URL", "Mission", "Lenses",
        "Score_Evocativeness", "Score_Novelty", "Score_Evidence",
        "User_Rating", "User_Status", "User_Comment"
    ]

    try:
        existing_headers = sheet.row_values(1)
        if existing_headers != expected_headers:
            sheet.update([expected_headers], 'A1')
    except Exception as e:
        print(f"⚠️ Header Check Failed: {e}")


def detect_missions_from_text(message: str) -> List[str]:
    """Lightweight mission detection based on explicit mission names."""
    message_lower = message.lower()
    return [mission for mission in MISSION_KEYWORDS if mission.lower() in message_lower]


def sample_keywords(keyword_pool: List[str], sample_size: int, rng: random.Random) -> List[str]:
    if not keyword_pool:
        return []
    unique = [kw for kw in keyword_pool if kw.strip()]
    if len(unique) <= sample_size:
        return unique
    return rng.sample(unique, sample_size)


def get_mission_keywords(message: str, requested_signals: Optional[int] = None) -> str:
    """Load mission-specific keyword hints and randomize them for breadth."""
    rng = random.Random()
    sample_size = max(6, min(14, (requested_signals or 6) * 2))

    missions_requested = detect_missions_from_text(message)
    broad_terms = ("broad", "scan", "general", "all missions", "any mission", "across missions")
    broad_scan_requested = any(term in message.lower() for term in broad_terms)
    mission_scope = missions_requested if missions_requested else list(MISSION_KEYWORDS.keys())

    prompt_parts = ["### NESTA MISSION KEYWORD HINTS (ROTATE ACROSS THESE FOR DISTINCT SIGNALS):"]

    for mission in mission_scope:
        selected = sample_keywords(MISSION_KEYWORDS.get(mission, []), sample_size, rng)
        if selected:
            prompt_parts.append(
                f"- {mission}: use a different keyword from this list per card to avoid overlap — {', '.join(selected)}"
            )

    # Broader scans get a mix from other missions to encourage novel, cross-mission discovery.
    if broad_scan_requested and missions_requested and len(mission_scope) == 1:
        other_missions = [m for m in MISSION_KEYWORDS if m not in mission_scope]
        for mission in other_missions:
            selected = sample_keywords(MISSION_KEYWORDS.get(mission, []), max(3, sample_size // 2), rng)
            if selected:
                prompt_parts.append(
                    f"- Additional breadth ({mission}): sprinkle in occasionally — {', '.join(selected)}"
                )

    cross_terms = sample_keywords(CROSS_CUTTING_KEYWORDS, max(5, sample_size // 2), rng)
    if cross_terms:
        prompt_parts.append(
            f"- CROSS-CUTTING (to make sources richer and more novel): {', '.join(cross_terms)}"
        )

    prompt_parts.append(
        "Use these keywords to keep searches on-mission and make each signal distinct."
    )
    return "\n".join(prompt_parts)


def get_topic_adjacent_keywords(message: str, limit: int = 12) -> List[str]:
    """Extract mission keywords that relate to user-provided topic tokens."""
    tokens = [t for t in re.split(r"[^a-z0-9]+", message.lower()) if len(t) >= 4]
    if not tokens:
        return []

    related: List[str] = []
    for kw in CROSS_CUTTING_KEYWORDS:
        kw_lower = kw.lower()
        if any(token in kw_lower for token in tokens) and kw not in related:
            related.append(kw)

    for keywords in MISSION_KEYWORDS.values():
        for kw in keywords:
            kw_lower = kw.lower()
            if any(token in kw_lower for token in tokens) and kw not in related:
                related.append(kw)

            if len(related) >= limit:
                break
        if len(related) >= limit:
            break

    return related[:limit]

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
                raw_rating = r.get('User_Rating', 3)
                rating = int(raw_rating) if str(raw_rating).strip() != "" else 3
                
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
    # Default to 1 month if unknown to keep results fresh
    return mapping.get(filter_text, "m1")


def get_sheet_records(include_rejected: bool = False) -> List[Dict[str, Any]]:
    """Return sheet records with row numbers; optionally filter out rejected signals."""
    sheet = get_google_sheet()
    if not sheet:
        return []

    ensure_sheet_headers(sheet)

    try:
        rows = sheet.get_all_values()
        if not rows:
            return []

        headers = rows[0]
        records = []
        for idx, row in enumerate(rows[1:], start=2):
            if all(cell == "" for cell in row):
                continue
            record = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
            record["_row"] = idx
            status = str(record.get("User_Status", "")).lower()
            if not include_rejected and status == "rejected":
                continue
            records.append(record)
        return records
    except Exception as e:
        print(f"Read Error: {e}")
        return []


def upsert_signal(signal: Dict[str, Any]) -> None:
    """Create or update a signal row without duplicating by URL or Title."""
    sheet = get_google_sheet()
    if not sheet:
        raise RuntimeError("Sheet unavailable")

    ensure_sheet_headers(sheet)

    payload = [
        signal.get("title", ""), signal.get("score", 0), signal.get("archetype", ""),
        signal.get("hook", ""), signal.get("url", ""), signal.get("mission", ""),
        signal.get("lenses", ""), signal.get("score_evocativeness", 0),
        signal.get("score_novelty", 0), signal.get("score_evidence", 0),
        signal.get("user_rating", 3), signal.get("user_status", "Pending"),
        signal.get("user_comment", "")
    ]

    try:
        records = get_sheet_records(include_rejected=True)
        match_row = None
        incoming_url = str(signal.get("url", "")).strip().lower()
        incoming_title = str(signal.get("title", "")).strip().lower()

        for rec in records:
            url = str(rec.get("URL", "")).strip().lower()
            title = str(rec.get("Title", "")).strip().lower()
            if incoming_url and url == incoming_url:
                match_row = rec.get("_row")
                break
            if incoming_title and title and title == incoming_title:
                match_row = rec.get("_row")
                break

        if match_row:
            sheet.update(f"A{match_row}:M{match_row}", [payload])
        else:
            sheet.append_row(payload)
    except Exception as e:
        print(f"Upsert Error: {e}")

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


async def perform_google_search(query, date_restrict="m1", requested_results: int = 8):
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

    # Cards must include tool-provided URLs to comply with the anti-hallucination policy.
    if not url:
        print("❌ Missing URL in tool output; skipping card to avoid unverifiable links.")
        return None
    
    tool_args["final_url"] = url
    tool_args["ui_type"] = "signal_card"
    return tool_args

# --- DATA MODELS ---

PREFERRED_NICHE_SOURCES = (
    "industry trade publications, academic preprints (arXiv, bioRxiv), scientific magazines, "
    "research blogs/Substack, specialist newsletters, technical standards bodies, and niche forums."
)


class ChatRequest(BaseModel):
    message: str
    time_filter: str = "Past Month"
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
    user_rating: Optional[int] = 3
    user_status: Optional[str] = "Pending"
    user_comment: Optional[str] = ""


class UpdateSignalRequest(BaseModel):
    url: Optional[str] = ""
    title: Optional[str] = ""
    user_rating: Optional[int] = 3
    user_status: Optional[str] = "Pending"
    user_comment: Optional[str] = ""

# --- ENDPOINTS ---

@app.get("/api/config")
def get_config():
    return {"sheet_url": SHEET_URL}

@app.get("/api/saved")
def get_saved_signals():
    return get_sheet_records(include_rejected=False)[::-1]

@app.post("/api/save")
def save_signal(signal: SaveSignalRequest):
    try:
        upsert_signal(signal.model_dump())
        return {"status": "success"}
    except Exception as e:
        print(f"Save Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/saved/{signal_id}")
def delete_signal(signal_id: int):
    return {"status": "ignored", "message": "Please delete directly from Google Sheets"}


@app.post("/api/update")
def update_signal(update: UpdateSignalRequest):
    try:
        existing = {
            "title": update.title or "",
            "url": update.url or "",
            "user_rating": update.user_rating if update.user_rating is not None else 3,
            "user_status": update.user_status or "Pending",
            "user_comment": update.user_comment or ""
        }

        if not existing["title"] and not existing["url"]:
            raise HTTPException(status_code=400, detail="Title or URL required to update a signal")

        # Preserve other columns by reading the current record
        records = get_sheet_records(include_rejected=True)
        match = None
        for rec in records:
            if (existing["url"] and str(rec.get("URL", "")) == existing["url"]) or (
                existing["title"] and str(rec.get("Title", "")) == existing["title"]
            ):
                match = rec
                break

        if match:
            merged = {
                "title": match.get("Title", existing["title"]),
                "score": match.get("Score", 0),
                "archetype": match.get("Archetype", ""),
                "hook": match.get("Hook", ""),
                "url": match.get("URL", existing["url"]),
                "mission": match.get("Mission", ""),
                "lenses": match.get("Lenses", ""),
                "score_evocativeness": match.get("Score_Evocativeness", 0),
                "score_novelty": match.get("Score_Novelty", 0),
                "score_evidence": match.get("Score_Evidence", 0),
                "user_rating": existing["user_rating"],
                "user_status": existing["user_status"],
                "user_comment": existing["user_comment"]
            }
            upsert_signal(merged)
            return {"status": "updated"}

        # If not found, save as new pending entry
        upsert_signal({
            "title": existing["title"],
            "url": existing["url"],
            "user_rating": existing["user_rating"],
            "user_status": existing["user_status"],
            "user_comment": existing["user_comment"]
        })
        return {"status": "created"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Update Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    try:
        print(f"Incoming Query: {req.message} | Filters: {req.time_filter}, TechMode: {req.tech_mode}")

        # 1. FETCH CONTEXT
        existing_titles = []
        existing_urls: Set[str] = set()
        learning_prompt = ""
        requested_signal_count = infer_requested_signal_count(req.message)
        mission_keyword_prompt = get_mission_keywords(req.message, requested_signal_count)
        topic_adjacent_keywords = get_topic_adjacent_keywords(req.message)
        search_result_target = determine_search_target_count(requested_signal_count)

        try:
            records = get_sheet_records(include_rejected=True)
            if records:
                existing_titles = [r.get("Title", "") for r in records][-80:]
                existing_urls = {str(r.get("URL", "")).strip().lower() for r in records if r.get("URL")}
                learning_prompt = get_learning_examples()
        except Exception as e:
            print(f"Context Fetch Warning: {e}")

        # 2. PROMPT CONSTRUCTION
        prompt = req.message
        
        # ✅ NEW: STRICT ANTI-HALLUCINATION INJECTION
        prompt += """

        SYSTEM PROTOCOL (DO NOT SKIP):
        1) You are in Research Mode. No search = no signal.
        2) Build 3–5 high-friction queries (Underground / Edge / Conflict) PLUS at least one exact match search for the user's topic.
        3) For EACH query, call perform_web_search with the current time horizon.
        4) Keep only results with a direct article URL; copy the URL exactly. Reject homepages or vague links.
        5) Discard anything outside the requested time horizon.
        6) If tech mode is on: search ONLY hard tech (hardware, biotech, materials, code). If source types are provided, prioritize them.
        7) Exclude any title in this blocklist: [titles…].
        8) Repeat searches and refinements until you have exactly N verified signals (if N requested). If none qualify, say “No verified signals found.”
        CHECKLIST BEFORE RESPONDING: every signal has a tool-returned URL; URL fits time horizon; title not blocked; hook is plain-English and states why Nesta should care; count matches request.

        """

        prompt += "\n\nBROAD COVERAGE AND NOVELTY:\n- Use different mission keywords per card to guarantee distinct signals.\n- If searches stall, pivot to adjacent mission or cross-cutting keywords while keeping the user's topic in scope."

        prompt += f"\n\nPRIMARY TOPIC (SEARCH EXACTLY AS WRITTEN IN AT LEAST ONE QUERY): \"{req.message.strip()}\""

        prompt += (
            "\n\nSOURCE PRIORITY: Bias searches toward niche and technical sources ("
            f"{PREFERRED_NICHE_SOURCES}). Avoid generic front pages or mass-media summaries unless they contain a new primary source link."
            " Include site, publisher, and publication date in reasoning to prove recency."
        )

        prompt += (
            "\n\nDELIVERY FORMAT (FOR EACH SIGNAL):"
            "\n- Signal: What is the thing (concise title)."
            "\n- Source: URL copied verbatim from search output (include publisher and date)."
            "\n- Mission Link: Explicitly state which Nesta mission(s) this serves and why."
            "\n- Hook (plain-English, jargon-free): Lead with an engaging sentence that explains the breakthrough in everyday language, expands acronyms, and spells out the mission-specific implication for Nesta (why we should care)."
            "\n- Why Important: 1–2 sentences on impact/relevance (so-what for Nesta teams)."
            "\n- Ratings: Provide 1–10 scores for Relevance, Credibility, and Novelty (could Nesta have found it easily?)."
            "\nPopulate these as structured fields when calling display_signal_card (e.g., hook, rating_relevance, rating_credibility, rating_novelty)."
        )
        
        if learning_prompt:
            prompt += f"\n\n{learning_prompt}"
            prompt += "\nINSTRUCTION: Analyze the 'User Notes' and style of the examples above. Adjust your search strategy to match this taste profile."

        prompt += "\n\nSYSTEM INSTRUCTION: You currently have 0 verified signals. You MUST use the 'perform_web_search' tool to find real articles before generating any cards. Do not generate cards from memory."

        if mission_keyword_prompt:
            prompt += f"\n\n{mission_keyword_prompt}"
            prompt += (
                "\nMANDATE: Use the keyword lines above to steer searches so every signal directly relates to Nesta's missions (A Fairer Start, A Healthy Life, A Sustainable Future)."
                " If the request is broad, rotate across missions; if it targets one mission, randomize within that mission and avoid repeating keywords across cards."
            )

        if topic_adjacent_keywords:
            prompt += "\n\nTOPIC-ADJACENT KEYWORDS (deploy if exact topic queries are sparse): "
            prompt += ", ".join(topic_adjacent_keywords)

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
        seen_urls: Set[str] = set()
        seen_titles: Set[str] = set()

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
                        url_key = processed_card.get("final_url", "").strip().lower() if processed_card else ""
                        title_key = processed_card.get("title", "").strip().lower() if processed_card else ""

                        if processed_card and url_key and url_key not in seen_urls and url_key not in existing_urls and title_key not in seen_titles:
                            accumulated_signals.append(processed_card)
                            seen_urls.add(url_key)
                            existing_urls.add(url_key)
                            if title_key:
                                seen_titles.add(title_key)
                            tool_outputs.append({
                                "tool_call_id": tool.id,
                                "output": json.dumps({"status": "displayed"})
                            })

                            # Autosave to the sheet without duplicating
                            try:
                                upsert_signal({
                                    "title": processed_card.get("title"),
                                    "score": processed_card.get("score", 0),
                                    "archetype": processed_card.get("archetype", ""),
                                    "hook": processed_card.get("hook", ""),
                                    "url": processed_card.get("final_url", ""),
                                    "mission": processed_card.get("mission", ""),
                                    "lenses": processed_card.get("lenses", ""),
                                    "score_evocativeness": processed_card.get("score_evocativeness", 0),
                                    "score_novelty": processed_card.get("score_novelty", 0),
                                    "score_evidence": processed_card.get("score_evidence", 0),
                                    "user_status": "Pending"
                                })
                            except Exception as e:
                                print(f"Autosave Warning: {e}")

                        elif processed_card:
                            tool_outputs.append({
                                "tool_call_id": tool.id,
                                "output": json.dumps({"status": "skipped_duplicate"})
                            })
                        else:
                            tool_outputs.append({
                                "tool_call_id": tool.id,
                                "output": json.dumps({"status": "skipped_missing_url"})
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
