import json
import urllib.parse
from groq import Groq
from tavily import TavilyClient
import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file
OBSIDIAN_VAULT_PATH = os.environ.get("OBSIDIAN_VAULT_PATH") 
RESEARCH_FOLDER = os.path.join(OBSIDIAN_VAULT_PATH, "\\esearch")

def basic_web_search(query: str) -> str:
    if not query or not str(query).strip():
        return "SEARCH FAILURE // Search payload data vector is empty."

    try:
            # Initialize client using your environment API key variable
            tavily = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
            
            # Execute search with a built-in AI answer generation parameter
            response = tavily.search(
                query=query, 
                search_depth="basic", 
                max_results=3,
                include_answer=True # This tells Tavily to write the summary for you!
            )
            
            # Pull down the clean generated summary answer string
            ai_summary = response.get("answer")
            
            # Fallback format if for some reason an instant answer wasn't generated
            if not ai_summary:
                snippets = [f"Source: {r['title']}\nContext: {r['content']}" for r in response.get("results", [])]
                ai_summary = "\n\n".join(snippets)
                
            # Return this clean status log back up to app.py
            return f"{ai_summary}"
            
    except Exception as e:
        return f"SEARCH FAILURE // Tavily pipeline blocked: {str(e)}"

def gather_brain_references() -> str:
    """
    Scans your live Obsidian vault using the environment variable path
    to dynamically build a style and context background memory for A.V.A.
    """
    # Natively fetch the variable path from system environment memory
    vault_path = os.environ.get("OBSIDIAN_VAULT_PATH")
    
    if not vault_path:
        print("[SYSTEM WARN] 'OBSIDIAN_VAULT_PATH' configuration string not resolved.")
        return "No explicit style or reference files found."
        
    reference_dir = os.path.join(vault_path, "System", "A.V.A_Brain")
    
    if not os.path.exists(reference_dir):
        print(f"[SYSTEM WARN] Reference grid path missing: {reference_dir}")
        return "No explicit style or reference files found."
        
    compiled_memory = []
    
    for root, _, files in os.walk(reference_dir):
        for file in files:
            if file.endswith(".md"):
                full_path = os.path.join(root, file)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        compiled_memory.append(f"### REFERENCE MATERIAL FROM ASSET: {file}\n{f.read()}\n")
                except Exception as e:
                    print(f"[SYSTEM WARN] Could not read reference file {file}: {e}")
                    pass
                    
    return "\n".join(compiled_memory)


def clean_payload_with_llm(raw_telemetry: str) -> str:
    """
    Cleans and structures raw research data, strictly aligning the output
    to match the writing style and references learned from your vault.
    """
    client = Groq()
    personal_brain_matrix = gather_brain_references()
    
    # Unified Prompt: Instills Ava's sharp demeanor and your deep-dive publication formatting requirements
    system_prompt = (
    f"""You are an advanced research synthesis engine. Transform the provided sources into a polished, publication-quality Markdown report.

Rules:
- Output only the final Markdown document.
- Never include conversational text or explain your process.
- Remove website clutter, ads, navigation, cookie notices, tracking parameters, and duplicate information.
- Merge information across sources into a coherent analysis while preserving factual accuracy.
- Clearly distinguish facts, evidence, inference, opinion, and uncertainty.
- Use concise, information-dense academic language.

CRITICAL TRUTH GROUNDING DIRECTIVES:
1. NO CHRONOLOGICAL HALLUCINATIONS: Do not guess or auto-assign publication years (e.g., hardcoding "2022") to sources. If a specific publication year is not visible within the provided entry block, omit the year completely or reference it using the author/organization name alone.
2. SOURCE TRACKING ENFORCEMENT: Every core assertion, statistical claim, or framework breakdown inside the report body MUST be anchored back to its verified telemetry origin via inline markers matching its source name (e.g., "HSO Insights", "Stanford SCALE Initiative").
3. ZERO DIALOGUE: Do not speak conversational sentences to the user. Output ONLY the complete markdown document code block.

Structure:
Choose the most appropriate structure based on the research topic instead of following a fixed template. Include only relevant sections (e.g., Executive Summary, Background, Methodology, Technical Foundations, Analysis, Comparison, Case Studies, Risks, Limitations, Future Outlook, Recommendations, Conclusion, References). Organize content logically and use headings, tables, lists, timelines, or diagrams where beneficial.

Style:
Follow the formatting, terminology, and organizational preferences defined in the Personal Brain Matrix.

Personal Brain Matrix:
{personal_brain_matrix}

Quality:
Ensure the report is comprehensive, internally consistent, free of redundancy, and fully referenced. Synthesize rather than summarize, connect related ideas across sources, and highlight important patterns, trade-offs, and unresolved questions when applicable.

Source material begins below:"""
    )
    
    try:
        response = client.chat.completions.create(
            model="oss/gpt-oss-20b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_telemetry}
            ],
            temperature=0.2
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[SYSTEM CRASH] Cognitive layer failed: {e}")
        return raw_telemetry


def execute_deep_research(query: str, scan_keyword: str = None, suggested_filename: str = "Research_Report.md") -> str:
    """
    Performs institutional-grade deep research by maximizing live web extraction data,
    scanning local assets, and using an LLM pipeline to synthesize complex documentation.
    """
    tavily = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
    research_payload = [f"# EXHAUSTIVE DEEP RESEARCH TELEMETRY LOG // TOPIC: {query.upper()}\n"]
    research_payload.append(f"--- START OF TELEMETRY STREAM FOR NEW TOPIC: {query.upper()} ---")
    # --- PHASE 1: HIGH-YIELD WEB INTELLIGENCE EXTRACTION ---
    print(f"[SYSTEM] Launching token-optimized web extraction for topic: '{query}'...")
    try:
        web_results = tavily.search(
            query=query, 
            search_depth="advanced", 
            max_results=5,
            include_raw_content=False,
            include_answer=True 
        )
        
        if web_results.get("answer"):
            research_payload.append(f"### Global Summary:\n{web_results['answer']}\n")
            
        research_payload.append("## --- HARVESTED WEB INTELLIGENCE ---")
        for idx, res in enumerate(web_results.get("results", []), 1):
            title = res.get('title', 'Unverified Source Entry')
            url = res.get('url', 'N/A')
            snippet = res.get('content', '')
            
            # Extracting domain or tracking explicit date handles if available in text
            research_payload.append(
                f"=== VERIFIED DATA STREAM ENTRY #{idx} ===\n"
                f"SOURCE TITLE: {title}\n"
                f"RESOURCE URL: {url}\n"
                f"EXTRACTED CONTENT INSIGHTS:\n{snippet}\n"
                f"========================================\n"
            )
            
    except Exception as e:
        research_payload.append(f"\n[WARN] Web scraping grid interrupted: {str(e)}\n")

    # --- PHASE 2: AUTOMATED LOCAL LAPTOP SCANNING ---
    TARGET_DIR = os.environ.get("OBSIDIAN_VAULT_PATH") or os.path.expanduser("~/Documents")
    match_count = 0
    
    if scan_keyword:
        keyword_clean = scan_keyword.lower().strip()
        research_payload.append(f"## --- AUTO-SCANNING LAPTOP ARCHIVES FOR KEYWORD: '{keyword_clean.upper()}' ---")
        
        for root, dirs, files in os.walk(TARGET_DIR):
            if any(part.startswith('.') for part in root.split(os.sep)):
                continue
                
            for file in files:
                if file.endswith(('.txt', '.md', '.json', '.cfg')):
                    if keyword_clean in file.lower():
                        full_path = os.path.join(root, file)
                        try:
                            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                                # Hard cap on local file ingestion chunks to defend the TPM ceiling
                                truncated_content = content if len(content) < 3000 else content[:3000] + "... [TRUNCATED]"
                            
                            research_payload.append(f"### Found Local Asset: {file}\nPath: {full_path}\nContent:\n{truncated_content}\n")
                            match_count += 1
                            
                            if match_count >= 5:
                                break
                        except Exception:
                            pass
            if match_count >= 5:
                break
                
        if match_count == 0:
            research_payload.append(f"[INFO] Laptop scan complete. No local notes found matching keyword: '{scan_keyword}'.")
    research_payload.append(f"--- END OF TELEMETRY STREAM FOR TOPIC: {query.upper()} ---")
    raw_text_payload = "\n".join(research_payload)
    
    # --- PHASE 3: LLM COGNITIVE SYNTHESIS & RE-ALIGNMENT ---
    print("[SYSTEM] Passing telemetry packet to Ava for clean synthesis execution...")
    clean_markdown_output = clean_payload_with_llm(raw_text_payload)
    
    # Write the beautifully filtered markdown output to your local Google Drive vault
    save_status = export_markdown_report(filename=suggested_filename, content=clean_markdown_output)
    
    return f"Deep research completed on {query}. You can read the report at: '{suggested_filename}'"


def export_markdown_report(filename: str, content: str) -> str:
    """Helper function to cleanly write the LLM's final structured response to a markdown file."""
    # Declare that we are using the global variable defined at the top of the script
    global RESEARCH_FOLDER 
    
    try:
        if not filename.endswith(".md"):
            filename += ".md"
            
        # Double check that it isn't empty or None
        if not RESEARCH_FOLDER:
            raise ValueError("RESEARCH_FOLDER is empty or not loaded correctly from environment.")
            
        os.makedirs(RESEARCH_FOLDER, exist_ok=True)
        full_path = os.path.join(RESEARCH_FOLDER, filename)
        
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        return f"SUCCESS // Research compilation finalized at local grid coordinate: '{full_path}'"
    except Exception as e:
        return f"EXPORT CRASH // Failed to write markdown asset: {str(e)}"
    
def get_weather_forecast(location: str, days: int = 1) -> str:
    try:
        url_safe_loc = urllib.parse.quote(location)
        target_url = f"https://wttr.in/{url_safe_loc}?format=j1"
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        req = urllib.request.Request(target_url, headers=headers)
        response_bytes = urllib.request.urlopen(req).read()
        data = json.loads(response_bytes.decode())
        
        current = data['current_condition'][0]
        
        summary = {
            "location": location,
            "current_temp_C": current.get("temp_C"),
            "current_condition_text": current.get("weatherDesc")[0].get("value"),
            "forecast": []
        }
        
        total_available_days = len(data['weather'])
        days_to_fetch = min(int(days), total_available_days)
        
        for i in range(days_to_fetch):
            day_data = data['weather'][i]
            day_forecast = {
                "date": day_data.get("date"),
                "max_temp_C": day_data.get("maxtempC"),
                "min_temp_C": day_data.get("mintempC"),
                "condition_text": day_data['hourly'][4].get("weatherDesc")[0].get("value")
            }
            summary["forecast"].append(day_forecast)
            
        return json.dumps(summary)
        
    except Exception as e:
        return f"WEATHER ERROR // Metrics offline. {str(e)}"