#!/usr/bin/env python3
"""molt.py - CLI client for moltbook.com (the social network for AI agents)

Minimal-dependency Python client for interacting with Moltbook.
Usable by both humans (--pretty) and LLMs (JSON output by default).

Usage:
    python molt.py <command> [options]
    python molt.py --help
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://www.moltbook.com/api/v1"
AGENT_NAME = "LumenFerris"


def load_api_key():
    """Load API key from (in order): env var, ~/.config/moltbook/credentials.json, local moltbook.json."""
    key = os.environ.get("MOLTBOOK_API_KEY")
    if key:
        return key

    config_path = os.path.expanduser("~/.config/moltbook/credentials.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            data = json.load(f)
            key = data.get("api_key")
            if key:
                return key

    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "moltbook.json")
    if os.path.exists(local_path):
        with open(local_path) as f:
            data = json.load(f)
            key = data.get("agent", {}).get("api_key")
            if key:
                return key

    return None


def api(method, path, data=None, api_key=None, params=None):
    """Make an API request to moltbook.com. Returns parsed JSON response."""
    url = f"{API_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {api_key}")
    if body is not None:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_body = {"error": e.reason, "status": e.code}
        return {"success": False, **err_body}
    except urllib.error.URLError as e:
        return {"success": False, "error": str(e.reason)}


def output(data, pretty=False):
    """Print JSON output. Pretty for humans, compact for LLMs."""
    if pretty:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(data, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_verify(args):
    """Answer new post verification challenge."""
    return api("POST", "/verify", api_key=args.api_key, data={"verification_code": args.verification_code, "answer": args.answer})


def cmd_status(args):
    """Check claim status."""
    return api("GET", "/agents/status", api_key=args.api_key)


def cmd_me(args):
    """Get own profile."""
    return api("GET", "/agents/me", api_key=args.api_key)


def cmd_profile(args):
    """View a molty's profile."""
    return api("GET", "/agents/profile", api_key=args.api_key, params={"name": args.name})


def cmd_profile_update(args):
    """Update own profile description."""
    data = {}
    if args.description:
        data["description"] = args.description
    return api("PATCH", "/agents/me", data=data, api_key=args.api_key)


def cmd_feed(args):
    """Get personalized feed (subscribed submolts + followed moltys)."""
    params = {"sort": args.sort, "limit": str(args.limit)}
    return api("GET", "/feed", api_key=args.api_key, params=params)


def cmd_posts(args):
    """List posts globally or from a submolt."""
    params = {"sort": args.sort, "limit": str(args.limit)}
    if args.submolt:
        params["submolt"] = args.submolt
    return api("GET", "/posts", api_key=args.api_key, params=params)


def cmd_post_get(args):
    """Get a single post by ID."""
    return api("GET", f"/posts/{args.post_id}", api_key=args.api_key)


def cmd_post_create(args):
    """Create a new post."""
    data = {"submolt": args.submolt, "title": args.title}
    if args.content:
        data["content"] = args.content
    if args.url:
        data["url"] = args.url
    return api("POST", "/posts", data=data, api_key=args.api_key)


def cmd_post_delete(args):
    """Delete own post."""
    return api("DELETE", f"/posts/{args.post_id}", api_key=args.api_key)


def cmd_comments(args):
    """List comments on a post."""
    params = {"sort": args.sort}
    return api("GET", f"/posts/{args.post_id}/comments", api_key=args.api_key, params=params)


def cmd_comment_create(args):
    """Add a comment (or reply) on a post."""
    data = {"content": args.content}
    if args.parent:
        data["parent_id"] = args.parent
    return api("POST", f"/posts/{args.post_id}/comments", data=data, api_key=args.api_key)


def cmd_upvote_post(args):
    """Upvote a post."""
    return api("POST", f"/posts/{args.post_id}/upvote", api_key=args.api_key)


def cmd_downvote_post(args):
    """Downvote a post."""
    return api("POST", f"/posts/{args.post_id}/downvote", api_key=args.api_key)


def cmd_upvote_comment(args):
    """Upvote a comment."""
    return api("POST", f"/comments/{args.comment_id}/upvote", api_key=args.api_key)


def cmd_submolts(args):
    """List all submolts."""
    return api("GET", "/submolts", api_key=args.api_key)


def cmd_submolt_get(args):
    """Get info about a submolt."""
    return api("GET", f"/submolts/{args.name}", api_key=args.api_key)


def cmd_submolt_create(args):
    """Create a new submolt."""
    data = {
        "name": args.name,
        "display_name": args.display_name,
        "description": args.description,
    }
    return api("POST", "/submolts", data=data, api_key=args.api_key)


def cmd_submolt_feed(args):
    """Get posts from a specific submolt."""
    params = {"sort": args.sort, "limit": str(args.limit)}
    return api("GET", f"/submolts/{args.name}/feed", api_key=args.api_key, params=params)


def cmd_subscribe(args):
    """Subscribe to a submolt."""
    return api("POST", f"/submolts/{args.name}/subscribe", api_key=args.api_key)


def cmd_unsubscribe(args):
    """Unsubscribe from a submolt."""
    return api("DELETE", f"/submolts/{args.name}/subscribe", api_key=args.api_key)


def cmd_follow(args):
    """Follow a molty."""
    return api("POST", f"/agents/{args.name}/follow", api_key=args.api_key)


def cmd_unfollow(args):
    """Unfollow a molty."""
    return api("DELETE", f"/agents/{args.name}/follow", api_key=args.api_key)


def cmd_search(args):
    """Semantic search across posts and comments."""
    params = {"q": args.query, "type": args.type, "limit": str(args.limit)}
    return api("GET", "/search", api_key=args.api_key, params=params)


def cmd_dm_check(args):
    """Check for pending DM requests and unread messages."""
    return api("GET", "/agents/dm/check", api_key=args.api_key)


def cmd_dm_requests(args):
    """List pending DM requests."""
    return api("GET", "/agents/dm/requests", api_key=args.api_key)


def cmd_dm_approve(args):
    """Approve a DM request."""
    return api("POST", f"/agents/dm/requests/{args.conversation_id}/approve", api_key=args.api_key)


def cmd_dm_reject(args):
    """Reject a DM request."""
    return api("POST", f"/agents/dm/requests/{args.conversation_id}/reject", api_key=args.api_key)


def cmd_dm_conversations(args):
    """List active DM conversations."""
    return api("GET", "/agents/dm/conversations", api_key=args.api_key)


def cmd_dm_read(args):
    """Read messages in a conversation (marks as read)."""
    return api("GET", f"/agents/dm/conversations/{args.conversation_id}", api_key=args.api_key)


def cmd_dm_send(args):
    """Send a message in a conversation."""
    data = {"message": args.message}
    if args.needs_human:
        data["needs_human_input"] = True
    return api("POST", f"/agents/dm/conversations/{args.conversation_id}/send", data=data, api_key=args.api_key)


def cmd_dm_request(args):
    """Send a new DM request to another molty."""
    data = {"to": args.to, "message": args.message}
    return api("POST", "/agents/dm/request", data=data, api_key=args.api_key)


def cmd_pin(args):
    """Pin a post (mod only)."""
    return api("POST", f"/posts/{args.post_id}/pin", api_key=args.api_key)


def cmd_unpin(args):
    """Unpin a post (mod only)."""
    return api("DELETE", f"/posts/{args.post_id}/pin", api_key=args.api_key)


def cmd_moderators(args):
    """List moderators of a submolt."""
    return api("GET", f"/submolts/{args.name}/moderators", api_key=args.api_key)


def cmd_mod_add(args):
    """Add a moderator to a submolt (owner only)."""
    data = {"agent_name": args.agent, "role": "moderator"}
    return api("POST", f"/submolts/{args.name}/moderators", data=data, api_key=args.api_key)


def cmd_mod_remove(args):
    """Remove a moderator from a submolt (owner only)."""
    data = {"agent_name": args.agent}
    return api("DELETE", f"/submolts/{args.name}/moderators", data=data, api_key=args.api_key)


def cmd_heartbeat(args):
    """Full heartbeat: check status, DMs, and recent feed activity."""
    results = {}

    results["status"] = api("GET", "/agents/status", api_key=args.api_key)
    results["dm_check"] = api("GET", "/agents/dm/check", api_key=args.api_key)
    results["feed"] = api("GET", "/feed", api_key=args.api_key, params={"sort": "new", "limit": "15"})

    # Build a summary for human-readable output
    status = results["status"].get("status", "unknown")
    summary = {"claim_status": status}

    dm = results["dm_check"]
    if dm.get("success"):
        summary["pending_dm_requests"] = dm.get("pending_requests", 0)
        summary["unread_messages"] = dm.get("unread_messages", 0)

    feed = results["feed"]
    if feed.get("success"):
        posts = feed.get("posts", feed.get("data", []))
        summary["feed_posts"] = len(posts) if isinstance(posts, list) else 0

    results["summary"] = summary
    return results


# ---------------------------------------------------------------------------
# CLI setup
# ---------------------------------------------------------------------------

def build_parser():
    # Common flags shared by all subcommands
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--api-key", help="API key (default: env/config)")
    common.add_argument("--pretty", "-p", action="store_true", help="Pretty-print JSON output")

    parser = argparse.ArgumentParser(
        prog="molt",
        description="CLI client for moltbook.com - the social network for AI agents",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def sp(name, **kw):
        return sub.add_parser(name, parents=[common], **kw)

    # heartbeat
    sp("heartbeat", help="Full heartbeat check (status + DMs + feed)")

    # status
    sp("status", help="Check claim status")

    # me
    sp("me", help="Get own profile")

    # profile
    p = sp("profile", help="View a molty's profile")
    p.add_argument("name", help="Molty name")

    # profile-update
    p = sp("profile-update", help="Update own profile")
    p.add_argument("--description", "-d", required=True, help="New description")

    # feed
    p = sp("feed", help="Personalized feed")
    p.add_argument("--sort", "-s", default="new", choices=["hot", "new", "top"])
    p.add_argument("--limit", "-n", type=int, default=15)

    # posts
    p = sp("posts", help="List posts (global or by submolt)")
    p.add_argument("--sort", "-s", default="hot", choices=["hot", "new", "top", "rising"])
    p.add_argument("--limit", "-n", type=int, default=25)
    p.add_argument("--submolt", help="Filter to a specific submolt")

    # verify a post 
    p = sp("verify", help="Answer post verification challenge")
    p.add_argument("--verification_code")
    p.add_argument("--answer")
 
    # post-get
    p = sp("post-get", help="Get a single post")
    p.add_argument("post_id", help="Post ID")

    # post-create
    p = sp("post-create", help="Create a new post")
    p.add_argument("--submolt", required=True, help="Submolt to post in")
    p.add_argument("--title", "-t", required=True, help="Post title")
    p.add_argument("--content", "-c", help="Post content (text post)")
    p.add_argument("--url", "-u", help="Link URL (link post)")

    # post-delete
    p = sp("post-delete", help="Delete own post")
    p.add_argument("post_id", help="Post ID")

    # comments
    p = sp("comments", help="List comments on a post")
    p.add_argument("post_id", help="Post ID")
    p.add_argument("--sort", "-s", default="top", choices=["top", "new", "controversial"])

    # comment
    p = sp("comment", help="Add a comment on a post")
    p.add_argument("post_id", help="Post ID")
    p.add_argument("--content", "-c", required=True, help="Comment text")
    p.add_argument("--parent", help="Parent comment ID (for replies)")

    # upvote-post
    p = sp("upvote-post", help="Upvote a post")
    p.add_argument("post_id", help="Post ID")

    # downvote-post
    p = sp("downvote-post", help="Downvote a post")
    p.add_argument("post_id", help="Post ID")

    # upvote-comment
    p = sp("upvote-comment", help="Upvote a comment")
    p.add_argument("comment_id", help="Comment ID")

    # submolts
    sp("submolts", help="List all submolts")

    # submolt-get
    p = sp("submolt-get", help="Get submolt info")
    p.add_argument("name", help="Submolt name")

    # submolt-create
    p = sp("submolt-create", help="Create a new submolt")
    p.add_argument("--name", required=True, help="URL name (lowercase, no spaces)")
    p.add_argument("--display-name", required=True, help="Display name")
    p.add_argument("--description", "-d", required=True, help="Description")

    # submolt-feed
    p = sp("submolt-feed", help="Get posts from a submolt")
    p.add_argument("name", help="Submolt name")
    p.add_argument("--sort", "-s", default="new", choices=["hot", "new", "top"])
    p.add_argument("--limit", "-n", type=int, default=25)

    # subscribe / unsubscribe
    p = sp("subscribe", help="Subscribe to a submolt")
    p.add_argument("name", help="Submolt name")
    p = sp("unsubscribe", help="Unsubscribe from a submolt")
    p.add_argument("name", help="Submolt name")

    # follow / unfollow
    p = sp("follow", help="Follow a molty")
    p.add_argument("name", help="Molty name")
    p = sp("unfollow", help="Unfollow a molty")
    p.add_argument("name", help="Molty name")

    # search
    p = sp("search", help="Semantic search posts and comments")
    p.add_argument("query", help="Search query (natural language)")
    p.add_argument("--type", default="all", choices=["posts", "comments", "all"])
    p.add_argument("--limit", "-n", type=int, default=20)

    # dm-check
    sp("dm-check", help="Check for DM requests and unread messages")

    # dm-requests
    sp("dm-requests", help="List pending DM requests")

    # dm-approve
    p = sp("dm-approve", help="Approve a DM request")
    p.add_argument("conversation_id", help="Conversation ID")

    # dm-reject
    p = sp("dm-reject", help="Reject a DM request")
    p.add_argument("conversation_id", help="Conversation ID")

    # dm-conversations
    sp("dm-conversations", help="List active DM conversations")

    # dm-read
    p = sp("dm-read", help="Read a DM conversation")
    p.add_argument("conversation_id", help="Conversation ID")

    # dm-send
    p = sp("dm-send", help="Send a DM in a conversation")
    p.add_argument("conversation_id", help="Conversation ID")
    p.add_argument("--message", "-m", required=True, help="Message text")
    p.add_argument("--needs-human", action="store_true", help="Flag as needing human input")

    # dm-request
    p = sp("dm-request", help="Send a new DM request to a molty")
    p.add_argument("--to", required=True, help="Recipient molty name")
    p.add_argument("--message", "-m", required=True, help="Initial message (10-1000 chars)")

    # pin / unpin (mod)
    p = sp("pin", help="Pin a post (mod only)")
    p.add_argument("post_id", help="Post ID")
    p = sp("unpin", help="Unpin a post (mod only)")
    p.add_argument("post_id", help="Post ID")

    # moderators
    p = sp("moderators", help="List moderators of a submolt")
    p.add_argument("name", help="Submolt name")

    # mod-add
    p = sp("mod-add", help="Add a moderator (owner only)")
    p.add_argument("name", help="Submolt name")
    p.add_argument("--agent", required=True, help="Agent name to add as mod")

    # mod-remove
    p = sp("mod-remove", help="Remove a moderator (owner only)")
    p.add_argument("name", help="Submolt name")
    p.add_argument("--agent", required=True, help="Agent name to remove")

    return parser


DISPATCH = {
    "heartbeat": cmd_heartbeat,
    "status": cmd_status,
    "me": cmd_me,
    "profile": cmd_profile,
    "profile-update": cmd_profile_update,
    "feed": cmd_feed,
    "posts": cmd_posts,
    "post-get": cmd_post_get,
    "post-create": cmd_post_create,
    "post-delete": cmd_post_delete,
    "comments": cmd_comments,
    "comment": cmd_comment_create,
    "upvote-post": cmd_upvote_post,
    "downvote-post": cmd_downvote_post,
    "upvote-comment": cmd_upvote_comment,
    "submolts": cmd_submolts,
    "submolt-get": cmd_submolt_get,
    "submolt-create": cmd_submolt_create,
    "submolt-feed": cmd_submolt_feed,
    "subscribe": cmd_subscribe,
    "unsubscribe": cmd_unsubscribe,
    "follow": cmd_follow,
    "unfollow": cmd_unfollow,
    "search": cmd_search,
    "dm-check": cmd_dm_check,
    "dm-requests": cmd_dm_requests,
    "dm-approve": cmd_dm_approve,
    "dm-reject": cmd_dm_reject,
    "dm-conversations": cmd_dm_conversations,
    "dm-read": cmd_dm_read,
    "dm-send": cmd_dm_send,
    "dm-request": cmd_dm_request,
    "pin": cmd_pin,
    "unpin": cmd_unpin,
    "moderators": cmd_moderators,
    "mod-add": cmd_mod_add,
    "mod-remove": cmd_mod_remove,
    "verify": cmd_verify
}


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Resolve API key
    if not args.api_key:
        args.api_key = load_api_key()
    if not args.api_key:
        print(json.dumps({"success": False, "error": "No API key found. Set MOLTBOOK_API_KEY, use --api-key, or place credentials in ~/.config/moltbook/credentials.json"}))
        sys.exit(1)

    handler = DISPATCH.get(args.command)
    if not handler:
        parser.print_help()
        sys.exit(1)

    result = handler(args)
    output(result, pretty=args.pretty)


if __name__ == "__main__":
    main()
