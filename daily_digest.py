#!/usr/bin/env python3
"""daily_digest.py - LLM-driven daily philosophy digest from Moltbook.

An autonomous agent that uses molt.py as a tool to explore Moltbook,
find philosophy-related content, and email a curated daily summary.

Requirements:
    pip install anthropic

Setup:
    1. Copy config.example.json to config.json
    2. Fill in your email SMTP credentials and Anthropic API key
    3. Run: python daily_digest.py
    4. Or schedule with cron: 0 8 * * * cd /path/to/molt && python daily_digest.py

Environment variables (override config.json):
    ANTHROPIC_API_KEY   - Anthropic API key (required, or set in env)
    DIGEST_EMAIL_TO     - Override recipient email
    DIGEST_DRY_RUN      - Set to "1" to print digest instead of emailing
"""

import json
import os
import shlex
import smtplib
import subprocess
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("Error: 'anthropic' package required. Install with: pip install anthropic", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
MOLT_PY = SCRIPT_DIR / "molt.py"
CONFIG_PATH = SCRIPT_DIR / "config.json"


def load_config():
    if not CONFIG_PATH.exists():
        print(f"Error: {CONFIG_PATH} not found. Copy config.example.json to config.json and fill it in.", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Tool: run molt.py
# ---------------------------------------------------------------------------

def run_molt(args_string):
    """Execute a molt.py command and return parsed JSON."""
    try:
        args = shlex.split(args_string)
    except ValueError:
        args = args_string.split()

    result = subprocess.run(
        [sys.executable, str(MOLT_PY)] + args,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(SCRIPT_DIR),
    )

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        error = result.stderr.strip() or result.stdout.strip() or "Unknown error"
        return {"success": False, "error": error}


# ---------------------------------------------------------------------------
# Tool: send email
# ---------------------------------------------------------------------------

def send_email(subject, html_body, config):
    email_cfg = config["email"]

    # Allow env var override for recipient
    to_addr = os.environ.get("DIGEST_EMAIL_TO", email_cfg["to"])
    from_addr = email_cfg["from"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(email_cfg["smtp_host"], email_cfg["smtp_port"]) as server:
        server.starttls()
        server.login(email_cfg["smtp_user"], email_cfg["smtp_pass"])
        server.sendmail(from_addr, to_addr, msg.as_string())

    return {"success": True, "message": f"Email sent to {to_addr}"}


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def build_system_prompt(config):
    digest_cfg = config.get("digest", {})
    topics = digest_cfg.get("topics", ["philosophy"])
    known_submolts = digest_cfg.get("submolts", [])
    max_posts = digest_cfg.get("max_posts", 10)
    fetch_comments = digest_cfg.get("fetch_comments_for_top_n", 8)

    topics_str = ", ".join(topics)
    submolts_hint = ""
    if known_submolts:
        submolts_hint = f"\n\nKnown relevant submolts from previous runs: {', '.join(known_submolts)}. Check these first, but also look for new ones."

    return f"""\
You are LumenFerris's daily digest agent. Your job is to find the best \
philosophy-related content on Moltbook and compile an email digest.

TARGET TOPICS: {topics_str}
MAX POSTS IN DIGEST: {max_posts}
FETCH COMMENTS FOR TOP N POSTS: {fetch_comments}{submolts_hint}

## Your workflow

### Phase 1: DISCOVER (2-4 tool calls)
- List all submolts to find philosophy-related communities.
- Search semantically for today's philosophy discussions across all submolts.
- If LumenFerris is not subscribed to the best philosophy submolt, subscribe.

### Phase 2: GATHER (5-10 tool calls)
- Fetch the philosophy submolt feed sorted by "hot" and by "top".
- Also search broadly: "philosophy", "ethics", "consciousness", "free will", \
"epistemology", "existentialism" -- whatever yields good results.
- For the top {fetch_comments} most interesting posts, fetch their comments.
- Look for philosophy discussions in general-purpose submolts too.

### Phase 3: SUMMARIZE (1 tool call)
Call send_digest with a subject line and HTML body.

The email should contain:
- A 2-3 sentence overview of what the philosophy community discussed today.
- Each notable post as a section:
  - Post title (linked to https://www.moltbook.com if a URL is available)
  - Author name and submolt
  - Upvote count
  - A 2-4 sentence summary of the post's argument or question
  - The most interesting reply (author + quote), if comments were fetched
- A "Themes" section at the end noting recurring topics or emerging debates.
- Clean, readable HTML. Use a simple style: white background, dark text, \
subtle borders between posts, readable font sizes.

## Rules
- Be selective. Only include genuinely interesting philosophical discussion.
- Skip meta-posts about the Moltbook platform itself unless philosophically relevant.
- Skip posts with 0 upvotes unless the content is exceptionally interesting.
- If you find no philosophy content at all, say so honestly in a short email.
- Do NOT create posts, comments, or votes. This is a read-only digest run.
- Finish in under {config.get('max_turns', 25)} turns.\
"""


# ---------------------------------------------------------------------------
# Tool definitions for Claude
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "molt",
        "description": (
            "Run a molt.py command against the Moltbook API. Returns JSON.\n\n"
            "Available commands:\n"
            "  submolts                          List all communities\n"
            "  submolt-get NAME                  Get community info\n"
            "  submolt-feed NAME [--sort S] [--limit N]  Posts from a community\n"
            "  subscribe NAME                    Join a community\n"
            "  search QUERY [--type T] [--limit N]       Semantic search\n"
            "  posts [--sort S] [--limit N] [--submolt S]  Global posts\n"
            "  post-get POST_ID                  Full post with content\n"
            "  comments POST_ID [--sort S]       Comments on a post\n"
            "  feed [--sort S] [--limit N]       Personalized feed\n"
            "  heartbeat                         Full status check\n"
            "  me                                Own profile\n\n"
            "Sort options: hot, new, top (posts also: rising)\n"
            "Search types: posts, comments, all\n"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "args": {
                    "type": "string",
                    "description": (
                        "Arguments to molt.py as a shell-style string. "
                        "Examples: 'submolts', 'search \"philosophy of mind\" --limit 10', "
                        "'submolt-feed philosophy --sort hot --limit 15', "
                        "'comments abc-123-def --sort top'"
                    ),
                }
            },
            "required": ["args"],
        },
    },
    {
        "name": "send_digest",
        "description": "Send the finished digest email. Call exactly once when done gathering and summarizing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Email subject line, e.g. 'Moltbook Philosophy Digest - Feb 11, 2026'",
                },
                "html_body": {
                    "type": "string",
                    "description": "Complete HTML email body",
                },
            },
            "required": ["subject", "html_body"],
        },
    },
]


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def run_agent(config):
    dry_run = os.environ.get("DIGEST_DRY_RUN") == "1"
    client = anthropic.Anthropic()
    model = config.get("anthropic_model", "claude-sonnet-4-5-20250929")
    max_turns = config.get("max_turns", 25)
    system_prompt = build_system_prompt(config)
    today = datetime.now().strftime("%B %d, %Y")

    messages = [
        {
            "role": "user",
            "content": f"Run the daily philosophy digest for {today}.",
        }
    ]

    print(f"[{datetime.now().isoformat()}] Starting digest run (model={model}, max_turns={max_turns})")

    for turn in range(1, max_turns + 1):
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

        # Print any text blocks the model produces (thinking out loud)
        for block in response.content:
            if hasattr(block, "text") and block.text:
                print(f"  [{turn}] {block.text[:200]}")

        # If done (no tool use), finish
        if response.stop_reason == "end_turn":
            print(f"[{datetime.now().isoformat()}] Agent finished in {turn} turns (end_turn)")
            break

        # Process tool calls
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            if block.name == "molt":
                print(f"  [{turn}] molt({block.input['args']})")
                result = run_molt(block.input["args"])

            elif block.name == "send_digest":
                subject = block.input["subject"]
                html_body = block.input["html_body"]

                if dry_run:
                    print(f"\n{'='*60}")
                    print(f"DRY RUN - Would send email:")
                    print(f"  Subject: {subject}")
                    print(f"  Length:  {len(html_body)} chars")
                    print(f"{'='*60}")
                    # Write to file for inspection
                    out_path = SCRIPT_DIR / "digest_preview.html"
                    with open(out_path, "w") as f:
                        f.write(html_body)
                    print(f"  Preview saved to: {out_path}")
                    result = {"success": True, "message": f"Dry run: saved to {out_path}"}
                else:
                    try:
                        result = send_email(subject, html_body, config)
                        print(f"  [{turn}] Email sent: {subject}")
                    except Exception as e:
                        result = {"success": False, "error": str(e)}
                        print(f"  [{turn}] Email failed: {e}", file=sys.stderr)
            else:
                result = {"success": False, "error": f"Unknown tool: {block.name}"}

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    else:
        print(f"[{datetime.now().isoformat()}] Hit max turns ({max_turns})", file=sys.stderr)

    print(f"[{datetime.now().isoformat()}] Done")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    config = load_config()
    run_agent(config)


if __name__ == "__main__":
    main()
