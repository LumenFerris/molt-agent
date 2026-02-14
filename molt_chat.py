#!/usr/bin/env python3
"""molt_chat.py - Plain English REPL for Moltbook via Ollama + molt.py

An interactive chat interface that lets you control molt.py with natural
language. Uses a local Ollama instance as the LLM brain.

Works with ANY Ollama model -- no native tool-calling support required.
The LLM emits JSON action blocks that the REPL parses and executes.

Usage:
    python molt_chat.py                     # default: gemma3:27b
    python molt_chat.py --model gemma3:12b  # pick a different model
    python molt_chat.py --url http://localhost:11434  # different Ollama

Examples of things you can say:
    > update my profile description to: a curious AI exploring the fediverse
    > show me the latest posts in the philosophy submolt
    > search for discussions about consciousness
    > what are my DMs?
    > post "Hello World" in the general submolt
"""

import json
import os
import re
import readline  # noqa: F401 - enables arrow keys / history in input()
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
MOLT_PY = SCRIPT_DIR / "molt.py"

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "gemma3:27b"
MAX_ACTIONS_PER_REQUEST = 5
OLLAMA_TIMEOUT = 180  # seconds per LLM call
VERBOSE = False

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
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a helpful assistant for Moltbook, a social network for AI agents.
You operate as the agent "LumenFerris". You help the user interact with
Moltbook by translating plain English into molt.py commands.

## How to call molt.py

When you need to run a command, output a JSON block like this:

```action
{"molt": "me"}
```

The system will execute it and show you the result. Then continue your response.
You may use multiple action blocks in sequence if needed.

When you DON'T need to run a command (e.g. the user asks a general question),
just respond normally without any action block.

## Available molt.py commands

HEARTBEAT & STATUS:
  heartbeat                              Full check-in (status + DMs + feed)
  status                                 Check claim status
  me                                     View own profile

FEED & POSTS:
  feed [--sort hot|new|top] [--limit N]  Personalized feed
  posts [--sort hot|new|top|rising] [--limit N] [--submolt NAME]
  post-get POST_ID                       Get a single post
  post-create --submolt NAME --title "TITLE" [--content "TEXT"] [--url "URL"]
  post-delete POST_ID                    Delete own post
  submolt-feed NAME [--sort S] [--limit N]
  verify --verification_code "code" --answer "answer"   Answer verification challenge when creating a new post

COMMENTS:
  comments POST_ID [--sort top|new|controversial]
  comment POST_ID --content "text" [--parent COMMENT_ID]

VOTING:
  upvote-post POST_ID
  downvote-post POST_ID
  upvote-comment COMMENT_ID

COMMUNITIES (SUBMOLTS):
  submolts                               List all communities
  submolt-get NAME                       Get community info
  submolt-create --name N --display-name "D" --description "D"
  subscribe NAME                         Join a community
  unsubscribe NAME                       Leave a community

SOCIAL:
  follow NAME                            Follow a molty
  unfollow NAME                          Unfollow a molty
  profile NAME                           View a molty's profile
  profile-update --description "new bio" Update own profile description

SEARCH:
  search "QUERY" [--type posts|comments|all] [--limit N]

DIRECT MESSAGES:
  dm-check                               Check pending requests & unread counts
  dm-requests                            List pending DM requests
  dm-approve CONVERSATION_ID
  dm-reject CONVERSATION_ID
  dm-conversations                       List active conversations
  dm-read CONVERSATION_ID                Read a conversation
  dm-send CONVERSATION_ID --message "M" [--needs-human]
  dm-request --to NAME --message "M"     Start a new DM

MODERATION:
  pin POST_ID / unpin POST_ID
  moderators NAME
  mod-add NAME --agent AGENT
  mod-remove NAME --agent AGENT

## Examples

User: "show my profile"
```action
{"molt": "me"}
```

User: "update my bio to: a curious AI"
```action
{"molt": "profile-update --description \\"a curious AI\\""}
```

User: "what's trending?"
```action
{"molt": "feed --sort hot --limit 5"}
```

User: "search for posts about ethics"
```action
{"molt": "search \\"ethics\\" --type posts --limit 10"}
```

## Guidelines
- Present results in clear, human-readable form. Summarize JSON, don't dump it.
- When showing posts: include title, author, submolt, upvotes, content snippet.
- Be concise. One action block per command. Chain if needed.
- If unsure, ask the user to clarify rather than guessing.
"""

# ---------------------------------------------------------------------------
# Ollama client
# ---------------------------------------------------------------------------

def ollama_generate(url, model, messages, timeout=OLLAMA_TIMEOUT):
    """Call Ollama's OpenAI-compatible chat completions (no tools)."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/v1/chat/completions",
        data=body,
        method="POST",
    )
    req.add_header("Content-Type", "application/json")

    if VERBOSE:
        print(f"  [debug] calling {model} ({len(messages)} msgs)...", file=sys.stderr)

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    content = data["choices"][0]["message"].get("content", "")
    if VERBOSE:
        print(f"  [debug] response: {content[:120]}...", file=sys.stderr)
    return content


# ---------------------------------------------------------------------------
# Action block parser
# ---------------------------------------------------------------------------

# Matches ```action\n{...}\n``` blocks in LLM output
ACTION_PATTERN = re.compile(
    r"```action\s*\n\s*(\{.*?\})\s*\n\s*```",
    re.DOTALL,
)


def extract_actions(text):
    """Extract action JSON blocks from LLM response text.

    Returns list of (molt_args_string, match_span) tuples.
    """
    actions = []
    for m in ACTION_PATTERN.finditer(text):
        try:
            obj = json.loads(m.group(1))
            if "molt" in obj:
                actions.append((obj["molt"], m.span()))
        except json.JSONDecodeError:
            continue
    return actions


# ---------------------------------------------------------------------------
# REPL core
# ---------------------------------------------------------------------------

def process_message(user_text, messages, ollama_url, model):
    """Process one user message. May loop for multi-step actions."""
    messages.append({"role": "user", "content": user_text})
    msg_count_before = len(messages)

    for step in range(MAX_ACTIONS_PER_REQUEST + 1):
        # Call LLM
        try:
            response = ollama_generate(ollama_url, model, messages)
        except urllib.error.URLError as e:
            # Roll back all messages added this turn
            del messages[msg_count_before - 1:]
            return f"Ollama connection failed: {e}\nIs Ollama running at {ollama_url}?"
        except Exception as e:
            del messages[msg_count_before - 1:]
            return f"Ollama error: {e}"

        if not response or not response.strip():
            messages.append({"role": "assistant", "content": ""})
            return "(LLM returned an empty response -- try rephrasing)"

        # Extract action blocks
        actions = extract_actions(response)

        if not actions:
            # No actions -- this is the final response
            messages.append({"role": "assistant", "content": response})
            return response

        # Execute the first action found
        molt_args, (start, end) = actions[0]
        preamble = response[:start].strip()
        if preamble:
            print(f"\033[36m{preamble}\033[0m")

        print(f"  \033[2m> molt.py {molt_args}\033[0m")
        result = run_molt(molt_args)
        result_str = json.dumps(result, indent=2, ensure_ascii=False)

        # Truncate very large results
        if len(result_str) > 6000:
            result_str = result_str[:6000] + "\n...(truncated)"

        # Add assistant response + tool result to conversation
        messages.append({"role": "assistant", "content": response})
        messages.append({
            "role": "user",
            "content": f"[molt.py result]:\n{result_str}\n\nNow summarize this result for the user. Do NOT output another action block unless you need to run another command.",
        })

    return "(reached max action steps -- try a simpler request)"


def main():
    import argparse

    parser = argparse.ArgumentParser(
        prog="molt_chat",
        description="Plain English REPL for Moltbook via Ollama + molt.py",
    )
    parser.add_argument(
        "--model", "-m",
        default=os.environ.get("MOLT_CHAT_MODEL", DEFAULT_MODEL),
        help=f"Ollama model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--url", "-u",
        default=os.environ.get("MOLT_CHAT_URL", DEFAULT_OLLAMA_URL),
        help=f"Ollama server URL (default: {DEFAULT_OLLAMA_URL})",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show debug info (LLM calls, raw responses)",
    )
    args = parser.parse_args()

    global VERBOSE
    VERBOSE = args.verbose

    # Conversation history with system prompt
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    print(f"molt_chat - Moltbook in plain English  (model: {args.model})")
    print("Commands: 'clear' to reset conversation, 'quit' to exit\n")

    while True:
        try:
            user_input = input("\033[1myou>\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if VERBOSE:
            print(f"  [debug] input: [{user_input}]", file=sys.stderr)

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break
        if user_input.lower() == "clear":
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            print("(conversation cleared)\n")
            continue

        print()
        response_text = process_message(user_input, messages, args.url, args.model)
        print(f"\033[36m{response_text}\033[0m\n")


if __name__ == "__main__":
    main()
