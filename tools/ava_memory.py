# ava_memory.py
# A.V.A. Long-Term Memory Core
#
# Facts are stored as a human-readable Obsidian markdown note - the .md file
# is the SOURCE OF TRUTH. You can open it in Obsidian, read it, fix a wrong
# fact, delete one, link it to other notes, whatever. On every write (and at
# import time) the facts get mirrored into a local ChromaDB collection so
# semantic search still works when A.V.A. retrieves relevant memory.
#
# Conversation history stays in ChromaDB only - it's a noisy rolling log,
# not something you'd want to hand-edit, so vector search alone is the right
# tool for that half.

import chromadb
import datetime
import uuid
import os
import re
from dotenv import load_dotenv

# ---------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------
# Point this at your actual Obsidian vault folder so the facts note shows up
# as a real, linkable, browsable note. Falls back to a local folder next to
# the app if you haven't set this up yet. You can also just hardcode your
# vault path directly instead of using an env var, e.g.:
#   OBSIDIAN_VAULT_PATH = r"C:\Users\Cherish\Documents\ObsidianVault"
load_dotenv()  # Load environment variables from .env file
OBSIDIAN_VAULT_PATH = os.environ.get("OBSIDIAN_VAULT_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "ava_vault"
)
FACTS_MD_PATH = os.path.join(OBSIDIAN_VAULT_PATH, "AVA Core Facts.md")

FACTS_HEADER = (
    "# A.V.A. Core Facts\n\n"
    "Facts A.V.A. remembers about you. Edit this file directly in Obsidian - "
    "add, fix, or delete a line and it's picked up next time facts are "
    "reindexed (happens automatically on startup, or call "
    "reindex_facts_from_markdown() manually).\n\n"
)

# Vector DB still used for: semantic search over facts, and all conversation history.
chroma_client = chromadb.PersistentClient(path="./ava_memory_store")

facts_collection = chroma_client.get_or_create_collection(
    name="core_facts",
    metadata={"hnsw:space": "cosine"}
)

convo_collection = chroma_client.get_or_create_collection(
    name="conversations",
    metadata={"hnsw:space": "cosine"}
)

# Matches a fact line written by _append_fact_line, e.g.:
# - [3f9e...-uuid] (general) I prefer dark mode. <!-- 2026-07-19T10:00:00 -->
_FACT_LINE_RE = re.compile(
    r"^- \[(?P<id>[0-9a-fA-F-]{36})\]\s*\((?P<category>[^)]*)\)\s*(?P<text>.+?)\s*<!--\s*(?P<ts>.+?)\s*-->\s*$"
)


# ---------------------------------------------------------------
# MARKDOWN FILE HELPERS
# ---------------------------------------------------------------
def _ensure_vault_file():
    os.makedirs(OBSIDIAN_VAULT_PATH, exist_ok=True)
    if not os.path.exists(FACTS_MD_PATH):
        with open(FACTS_MD_PATH, "w", encoding="utf-8") as f:
            f.write(FACTS_HEADER)


def _read_all_fact_lines() -> list[dict]:
    """Parses every fact bullet out of the markdown file into dicts:
    {'id', 'category', 'text', 'ts'}. Non-matching lines (headers, notes,
    blank lines) are simply skipped, so you can write whatever else you want
    in the file too."""
    _ensure_vault_file()
    facts = []
    with open(FACTS_MD_PATH, "r", encoding="utf-8") as f:
        for line in f:
            m = _FACT_LINE_RE.match(line.strip())
            if m:
                facts.append(m.groupdict())
    return facts


def _append_fact_line(fact_id: str, fact_text: str, category: str, timestamp: str):
    _ensure_vault_file()
    with open(FACTS_MD_PATH, "a", encoding="utf-8") as f:
        f.write(f"- [{fact_id}] ({category}) {fact_text} <!-- {timestamp} -->\n")


def _rewrite_fact_lines(facts: list[dict]):
    """Rewrites the whole file from a list of fact dicts - used after a delete."""
    _ensure_vault_file()
    with open(FACTS_MD_PATH, "w", encoding="utf-8") as f:
        f.write(FACTS_HEADER)
        for fact in facts:
            f.write(f"- [{fact['id']}] ({fact['category']}) {fact['text']} <!-- {fact['ts']} -->\n")


# ---------------------------------------------------------------
# STORE A CORE FACT
# Writes to the markdown file (source of truth) and mirrors into ChromaDB.
# ---------------------------------------------------------------
def store_fact(fact_text: str, category: str = "general") -> str:
    fact_text = " ".join(fact_text.split()).replace("-->", "->")  # keep it one safe line
    """Saves a permanent fact about the user as a markdown bullet, and embeds
    it into ChromaDB so semantic recall still works."""
    fact_id = str(uuid.uuid4())
    timestamp = datetime.datetime.now().isoformat()

    _append_fact_line(fact_id, fact_text, category, timestamp)

    facts_collection.add(
        documents=[fact_text],
        metadatas=[{"category": category, "timestamp": timestamp}],
        ids=[fact_id]
    )
    return f"MEMORY ENCODED // Stored: '{fact_text}'"


# ---------------------------------------------------------------
# DELETE A CORE FACT BY KEYWORD
# Facts are meant to be editable now, so give it a matching delete path.
# ---------------------------------------------------------------
def delete_fact(search_keyword: str) -> str:
    """Removes any fact whose text contains search_keyword, from both the
    markdown file and the vector index."""
    facts = _read_all_fact_lines()
    remaining = [f for f in facts if search_keyword.lower() not in f["text"].lower()]

    if len(remaining) == len(facts):
        return f"NO MATCH // No stored fact matches '{search_keyword}'."

    removed_ids = [f["id"] for f in facts if f["id"] not in {r["id"] for r in remaining}]
    _rewrite_fact_lines(remaining)
    if removed_ids:
        try:
            facts_collection.delete(ids=removed_ids)
        except Exception:
            pass
    return f"MEMORY WIPED // Removed fact(s) matching '{search_keyword}'."


# ---------------------------------------------------------------
# REINDEX FACTS FROM MARKDOWN
# Call on startup (already done automatically below) and any time you've
# hand-edited the .md file in Obsidian and want ChromaDB to catch up.
# ---------------------------------------------------------------
def reindex_facts_from_markdown() -> str:
    """Rebuilds the ChromaDB fact index straight from the markdown file - the
    file is the source of truth, so this is what makes hand-edits count."""
    facts = _read_all_fact_lines()

    existing_ids = facts_collection.get()["ids"]
    if existing_ids:
        facts_collection.delete(ids=existing_ids)

    if facts:
        facts_collection.add(
            documents=[f["text"] for f in facts],
            metadatas=[{"category": f["category"], "timestamp": f["ts"]} for f in facts],
            ids=[f["id"] for f in facts]
        )
    return f"REINDEX COMPLETE // {len(facts)} facts loaded from {FACTS_MD_PATH}"


# ---------------------------------------------------------------
# STORE A CONVERSATION EXCHANGE  (unchanged - ChromaDB only)
# ---------------------------------------------------------------
def store_conversation(user_input: str, ava_response: str) -> None:
    """Logs a conversation exchange for future context retrieval."""
    combined = f"User: {user_input} | A.V.A: {ava_response}"
    convo_collection.add(
        documents=[combined],
        metadatas=[{
            "timestamp": datetime.datetime.now().isoformat(),
            "user_input": user_input[:200]
        }],
        ids=[str(uuid.uuid4())]
    )


# ---------------------------------------------------------------
# RETRIEVE RELEVANT MEMORIES  (unchanged logic - still queries both banks)
# ---------------------------------------------------------------
def retrieve_relevant_memory(query: str, max_results: int = 3) -> str:
    """
    Semantically searches memory for anything relevant to the current query.
    Returns a formatted string ready to inject into A.V.A.'s system prompt.
    """
    results_text = []

    try:
        fact_results = facts_collection.query(
            query_texts=[query],
            n_results=min(max_results, facts_collection.count())
        )
        if fact_results["documents"][0]:
            for doc in fact_results["documents"][0]:
                results_text.append(f"[KNOWN FACT] {doc}")
    except Exception:
        pass

    try:
        convo_results = convo_collection.query(
            query_texts=[query],
            n_results=min(max_results, convo_collection.count())
        )
        if convo_results["documents"][0]:
            for doc in convo_results["documents"][0]:
                results_text.append(f"[PAST EXCHANGE] {doc}")
    except Exception:
        pass

    if not results_text:
        return ""

    return "Relevant memory context:\n" + "\n".join(results_text)


# ---------------------------------------------------------------
# LIST ALL STORED FACTS  -- reads straight from the markdown file
# ---------------------------------------------------------------
def list_all_facts() -> str:
    """Returns all stored core facts, read live from the markdown file."""
    facts = _read_all_fact_lines()
    if not facts:
        return "MEMORY CLEAR // No core facts stored."
    return "\n".join([f"• ({f['category']}) {f['text']}" for f in facts])


# ---------------------------------------------------------------
# WIPE CONVERSATION HISTORY (keep facts, clear chat log)
# ---------------------------------------------------------------
def clear_conversation_memory() -> str:
    """Clears rolling conversation logs but preserves core facts."""
    try:
        all_ids = convo_collection.get()["ids"]
        if all_ids:
            convo_collection.delete(ids=all_ids)
        return "CONVERSATION LOG PURGED // Core facts preserved."
    except Exception as e:
        return f"PURGE ERROR // {str(e)}"


# Build the ChromaDB fact index from the markdown file the moment this module
# loads, so retrieval works immediately without a manual reindex call, and so
# any hand-edits you made in Obsidian since last run take effect on restart.
reindex_facts_from_markdown()