from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..llm.router import LLMRouter
from ..memory.sqlite_store import SQLiteMemory


router = APIRouter(prefix="/llm", tags=["llm"])

# Singletons for simplicity
_llm_router = LLMRouter()
_memory = SQLiteMemory()


def _format_sse(data: Dict[str, Any]) -> bytes:
    # SSE lines must be "data: ..." + double newline
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


async def _retrieval_context(thread_id: Optional[str], query_preview: str) -> Optional[str]:
    # For now ignore thread_id and just search globally with the user's latest text
    try:
        results = await _memory.search(query_preview, top_k=5)
    except Exception:
        return None
    if not results:
        return None
    lines = []
    for item, score in results:
        lines.append(f"- ({score:.2f}) {item.text}")
    return "\n".join(lines)


@router.post("/chat")
async def chat(request: Request) -> StreamingResponse:
    """
    SSE streaming chat endpoint.
    Body JSON:
    {
      "mode": "quick|general|coding|deep" (optional),
      "messages": [{"role":"user|assistant|system","content":"..."}],
      "temperature": float?,
      "max_tokens": int?,
      "system": string?,               // overrides persona system if provided
      "remember": bool?,               // if true, persist last user message as memory
      "tools": bool?,                  // enable tool-calls
      "thread_id": string?             // for future thread-scoped memory
    }
    """
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    messages: List[Dict[str, Any]] = body.get("messages") or []
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="messages[] required")
    mode = body.get("mode")
    temperature = body.get("temperature")
    max_tokens = body.get("max_tokens")
    remember = bool(body.get("remember", False))
    tools_enabled = bool(body.get("tools", True))
    thread_id: Optional[str] = body.get("thread_id")

    # Normalize and pick the model
    messages = _llm_router.normalize_messages(messages)
    user_last = next((m for m in reversed(messages) if m.get("role") == "user"), None)
    user_text = user_last.get("content") if user_last else ""
    model = _llm_router.pick_model(mode, user_text)

    # Retrieval-augmented system
    retrieved = await _retrieval_context(thread_id, user_text or "")
    system_override = body.get("system")
    # Force a concise, tool-oriented system prompt that understands "from <email>"
    if not system_override:
        system_prompt = """You are Richard. Be concise. No <think> tags.

When asked to email:
- If the user says "from <email>", set account to that email.
- Draft: OUTPUT ONLY -> CALL_create_gmail_draft(to=["a@b.com"], subject="Subject", body_markdown="Content", account="sender@domain.com" optional)
- Send:  OUTPUT ONLY -> CALL_send_gmail(to=["a@b.com"], subject="Subject", body_markdown="Content", account="sender@domain.com" optional)
Do not add explanations or extra text. Output only the single function call."""
        if retrieved:
            system_prompt += f"\n\nContext: {retrieved}"
    else:
        system_prompt = system_override

    tools = _llm_router.default_tools(tools_enabled)
    # Extend tools with send_gmail and send_imessage so the model can explicitly choose proper channel
    if tools_enabled and isinstance(tools, list):
        tools.extend([
            {
                "type": "function",
                "function": {
                    "name": "send_gmail",
                    "description": "Send an email via orchestrator",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "account": {"type": "string"},
                            "to": {"type": "array", "items": {"type": "string"}},
                            "subject": {"type": "string"},
                            "body_markdown": {"type": "string"},
                        },
                        "required": ["to", "subject", "body_markdown"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "send_imessage",
                    "description": "Send an iMessage/SMS via orchestrator. Use group OR to[].",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "group": {"type": "string"},
                            "to": {"type": "array", "items": {"type": "string"}},
                            "body": {"type": "string"}
                        },
                        "required": ["body"],
                    },
                },
            },
        ])

    # Tool-call detection and dispatch helpers
    import re
    # Match single-line function calls, tolerate whitespace
    tool_call_pattern = re.compile(
        r"^CALL_(?P<name>[a-zA-Z0-9_]+)\((?P<args>.*)\)\s*$", re.DOTALL
    )
    # Safer subject/body extraction to avoid truncation when we pre-dispatch
    # Use quoted segments after explicit markers; fallback only if quoted not present.
    # Map natural language intents to tool calls by parsing addresses and fields from user text
    def intent_to_tool(user_text: str) -> Optional[Dict[str, Any]]:
        """
        Extract intent (send vs draft) and email fields directly from the user's utterance.
        No hard-coded recipients or content. Supports patterns like:
          - "send an email to a@b.com, c@d.com from me@x.com subject hi body hello there"
          - "draft email to a@b.com about Project X saying let's ship"
          - "send the monkey email" (falls back to model/tool output; no hardcoding)
        """
        if not user_text:
            return None
        import re as _re

        text = user_text.strip()
        low = text.lower()

        # Intent
        is_send = "send" in low
        is_draft = ("draft" in low) or ("create" in low)

        # Detect texting intent; if user mentions text/iMessage/SMS/message/chat, route to iMessage
        wants_text = any(k in low for k in (" text ", " imessage", " i-message", " sms ", " message", " chat "))
        # Detect explicit group/chat name in quotes
        group_match = _re.search(r'"([^"]+)"', text)
        group_name = group_match.group(1).strip() if group_match else None

        # Extract emails (all occurrences) and later split into to/account by heuristics
        emails = _re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)

        # from account — handle variants: "from <email>", "from the email <email>", "from email <email>"
        from_match = (
            _re.search(r"\bfrom\s+the\s+email\s+([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", text, flags=_re.IGNORECASE)
            or _re.search(r"\bfrom\s+email\s+([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", text, flags=_re.IGNORECASE)
            or _re.search(r"\bfrom\s+([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", text, flags=_re.IGNORECASE)
        )
        account = from_match.group(1) if from_match else None

        # to list: if "to" segment present, prefer addresses after "to"
        to_addrs: List[str] = []
        to_seg = _re.search(r"\bto\b(.+?)(?:\bsubject\b|\bsubj\b|\btitle\b|\bbody\b|\bcontent\b|$)", text, flags=_re.IGNORECASE)
        if to_seg:
            to_addrs = _re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", to_seg.group(1))
        # If still empty, and we have multiple emails, treat non-account ones as recipients
        if not to_addrs and emails:
            to_addrs = [e for e in emails if e != account]
        # If still ambiguous and exactly two emails present and one matches account, the other is the recipient
        if not to_addrs and account and len(emails) == 2:
            other = emails[0] if emails[1] == account else emails[1]
            if other != account:
                to_addrs = [other]

        # subject (prefer quoted title segments)
        subj = None
        subj_match_q = _re.search(r'\b(subject|subj|title)\b[^"]*"([^"]+)"', text, flags=_re.IGNORECASE)
        if subj_match_q:
            subj = subj_match_q.group(2).strip()
        else:
            subj_match = _re.search(r"\b(subject|subj|title)\b[: ]+(.+?)(?:\bbody\b|\bcontent\b|$)", text, flags=_re.IGNORECASE)
            if subj_match:
                subj = subj_match.group(2).strip().strip(' "\'')

        # body/content
        body = None
        # Accept phrasing like:
        # - body: "Hello world"
        # - body "Hello world"
        # - content "Hello world"
        # - message "Hello world"
        # - saying "Hello world"
        # - let's get the body to be "Hello world"
        body_match = (
            _re.search(r'\b(body|content|message|saying|say)\b[^"]*"([^"]+)"', text, flags=_re.IGNORECASE)
            or _re.search(r'\blet(\'|)s\s+get\s+the\s+body\s+to\s+be\s*"([^"]+)"', text, flags=_re.IGNORECASE)
            or _re.search(r'\b(body|content|message|saying|say)\b\s*[: ]+\s*([^\n\r]+)$', text, flags=_re.IGNORECASE)
            or _re.search(r'\blet(\'|)s\s+get\s+the\s+body\s+to\s+be\s*([^\n\r]+)$', text, flags=_re.IGNORECASE)
        )
        if body_match:
            # Take the last non-empty captured group that is not the marker token
            for g in reversed(body_match.groups()):
                if g and g.lower() not in ("body", "content", "message", "saying", "say", "'", "’"):
                    body = g.strip().strip(' "\'')
                    break

        # If we didn't match explicit markers, try lightweight fallbacks:
        # - If phrase like 'about X' appears, use as subject if subj empty
        if not subj:
            about_match = _re.search(r"\babout\b\s+(.+?)(?:\bfrom\b|\bto\b|\bbody\b|\bcontent\b|$)", text, flags=_re.IGNORECASE)
            if about_match:
                subj = about_match.group(1).strip().strip(' "\'')

        # Build args if we have at least recipients or explicit fields
        args: Dict[str, Any] = {}
        if account:
            args["account"] = account
        if to_addrs:
            args["to"] = to_addrs
        if subj:
            args["subject"] = subj
        if body:
            args["body_markdown"] = body

        # If user intends texting/iMessage:
        if wants_text:
            im_args: Dict[str, Any] = {}
            if group_name:
                im_args["group"] = group_name
            # If user listed phone/emails inline and didn't specify group, prefer recipients
            phones_or_emails = _re.findall(r'(?:\+?\d[\d\s\-]{7,}\d|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})', text)
            # Normalize: strip whitespace
            recipients = [p.strip() for p in phones_or_emails]
            if recipients and "group" not in im_args:
                im_args["to"] = recipients
            # Extract a quoted body if present; else use trailing phrase after saying/message/body markers
            body_q = _re.search(r'(?:(?:saying|message|body|content)\s*)"([^"]+)"', text, flags=_re.IGNORECASE)
            body_alt = _re.search(r'(?:saying|message|body|content)\s*[: ]+([^\n\r]+)$', text, flags=_re.IGNORECASE)
            im_body = (body_q.group(1).strip() if body_q else (body_alt.group(1).strip() if body_alt else None))
            if im_body:
                return {"name": "send_imessage", "args": {"group": im_args.get("group"), "to": im_args.get("to"), "body": im_body}}
            # If we cannot reliably extract a body, let the model emit a function call later
            return None

        # Decide tool (email path)
        # Only send if we have a minimally valid email: recipients and subject at least
        # Require body as well for send to avoid half-baked payloads
        if is_send and to_addrs and subj and body:
            return {"name": "send_gmail", "args": args}
        # If not enough to send, but have something, create a draft (allows iterative fill-in)
        if (is_send or is_draft) and (to_addrs or subj or body or account):
            return {"name": "create_gmail_draft", "args": args}

        return None

    def parse_args(arg_text: str) -> Dict[str, Any]:
        """
        Convert pseudo-Python args into a dict safely.
        Handles cases like:
          to=["a@b.com"], subject="Hi", body_markdown="Body", account="me@domain.com"
        Tolerates missing quotes on keys and mixed quotes on values.
        """
        import re
        try:
            s = arg_text.strip()

            # 1) Ensure keys are quoted: key= -> "key":
            s = re.sub(r'(^|,)\s*([A-Za-z_][A-Za-z0-9_]*)\s*=', r'\1"\2":', s)

            # 2) Convert Python-style True/False/None to JSON true/false/null
            s = re.sub(r'\bTrue\b', 'true', s)
            s = re.sub(r'\bFalse\b', 'false', s)
            s = re.sub(r'\bNone\b', 'null', s)

            # 3) Normalize quotes on string values
            s = re.sub(r'\'([^\'\\]*(?:\\.[^\'\\]*)*)\'', r'"\1"', s)

            # 4) Wrap into JSON object braces and parse
            json_like = "{" + s + "}"
            obj = json.loads(json_like)

            # 5) Normalize account: empty string -> remove
            if isinstance(obj.get("account"), str) and not obj["account"]:
                obj.pop("account", None)

            return obj
        except Exception as e:
            raise ValueError(f"Invalid tool args: {e}")

    async def dispatch_tool(name: str, args: Dict[str, Any]) -> str:
        # Wire up 4 functions: create_gmail_draft, send_gmail, create_calendar_event, create_notion_page
        import httpx
        BASE = "http://127.0.0.1:5273"  # call our own orchestrator routes

        # Normalize account if provided as empty string
        if isinstance(args.get("account"), str) and not args.get("account"):
            args.pop("account", None)

        # Emit structured debug logs for observability
        try:
            print(f"[dispatch_tool] name={name} args_in={json.dumps(args, ensure_ascii=False)}")
        except Exception:
            print(f"[dispatch_tool] name={name} args_in=<unserializable>")

        if name == "create_gmail_draft":
            # Build payload strictly from parsed/model-provided args; no hard-coded defaults
            payload = {
                "account": args.get("account"),
                "to": args.get("to", []),
                "subject": args.get("subject", ""),
                "body_markdown": args.get("body_markdown", ""),
            }
            print(f"[gmail.draft] payload={json.dumps(payload, ensure_ascii=False)}")
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    # Try primary route
                    r = await client.post(f"{BASE}/gmail/draft", json=payload)
                    print(f"[gmail.draft] POST {BASE}/gmail/draft -> {r.status_code}")
                    if r.status_code == 404:
                        # Fallback: some deployments expose a dev route
                        r = await client.post(f"{BASE}/dev/gmail/draft", json=payload)
                        print(f"[gmail.draft] POST {BASE}/dev/gmail/draft -> {r.status_code}")
                    r.raise_for_status()
                    data = r.json()
                    print(f"[gmail.draft] response={json.dumps(data, ensure_ascii=False)}")
                    draft_id = data.get('draft_id') or data.get('id')
                    if not draft_id:
                        return "Draft failed: missing draft id in response"
                    return f"Draft created: {draft_id}"
            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response is not None else "unknown"
                text = None
                try:
                    text = e.response.text
                except Exception:
                    pass
                print(f"[gmail.draft] HTTP error status={status} body={text}")
                return f"Draft failed: HTTP {status}"
            except Exception as e:
                print(f"[gmail.draft] error={e}")
                return f"Draft failed: {e}"

        if name == "send_gmail":
            # Build payload strictly from parsed/model-provided args; no hard-coded defaults
            payload = {
                "account": args.get("account"),
                "to": args.get("to", []),
                "subject": args.get("subject", ""),
                "body_markdown": args.get("body_markdown", ""),
            }

            # Strictly require account; do NOT infer. Ask user if missing.
            if not payload.get("account"):
                print(f"[gmail.send] missing 'account' -> cannot send")
                return "Send failed: missing sender account. Please specify 'from <email>' in your request."

            # Validate required fields before POST
            if not payload.get("to"):
                return "Send failed: missing recipient(s)."
            if not payload.get("subject"):
                return "Send failed: missing subject."
            if payload.get("body_markdown") in (None, ""):
                return "Send failed: missing body."

            print(f"[gmail.send] payload={json.dumps(payload, ensure_ascii=False)}")
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    r = await client.post(f"{BASE}/gmail/send", json=payload)
                    print(f"[gmail.send] POST {BASE}/gmail/send -> {r.status_code}")
                    if r.status_code == 404:
                        # Fallback attempt only if primary path not found
                        r = await client.post(f"{BASE}/dev/gmail/send", json=payload)
                        print(f"[gmail.send] POST {BASE}/dev/gmail/send -> {r.status_code}")
                    # If still not 2xx, raise and surface exact error
                    r.raise_for_status()
                    data = r.json()
                    print(f"[gmail.send] response={json.dumps(data, ensure_ascii=False)}")
                    # Validate presence of a message identifier to confirm send
                    msg_id = data.get("message_id") or data.get("id")
                    if not msg_id:
                        return "Send failed: missing message id in response"
                    return f"Email sent: {msg_id}"
            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response is not None else "unknown"
                text = None
                try:
                    text = e.response.text
                except Exception:
                    pass
                print(f"[gmail.send] HTTP error status={status} body={text}")
                return f"Send failed: HTTP {status}"
            except Exception as e:
                print(f"[gmail.send] error={e}")
                return f"Send failed: {e}"

        if name == "send_imessage":
            try:
                import httpx
                payload = {}
                if args.get("group"):
                    payload = {"group": args.get("group"), "body": args.get("body")}
                elif args.get("to"):
                    payload = {"to": args.get("to"), "body": args.get("body")}
                elif args.get("chat_id"):
                    payload = {"chat_id": args.get("chat_id"), "body": args.get("body")}
                else:
                    return "Text failed: missing group/to/chat_id."
                if not payload.get("body"):
                    return "Text failed: missing body."

                async with httpx.AsyncClient(timeout=60.0) as client:
                    r = await client.post("http://127.0.0.1:5273/imessage/send", json=payload)
                    print(f"[imessage.send] POST /imessage/send -> {r.status_code}")
                    r.raise_for_status()
                    data = r.json()
                    return f"Message sent: {data.get('detail') or 'ok'}"
            except Exception as e:
                return f"Text failed: {e}"

        if name == "create_calendar_event":
            try:
                import httpx
                async with httpx.AsyncClient(timeout=60.0) as client:
                    r = await client.post(
                        "http://127.0.0.1:5273/calendar/create",
                        json=args,
                    )
                    r.raise_for_status()
                    data = r.json()
                    return f"Event created: {data.get('htmlLink') or data.get('event_id') or 'ok'}"
            except Exception as e:
                return f"Calendar failed: {e}"

        if name == "create_notion_page":
            try:
                import httpx
                async with httpx.AsyncClient(timeout=60.0) as client:
                    r = await client.post(
                        "http://127.0.0.1:5273/notion/create",
                        json=args,
                    )
                    r.raise_for_status()
                    data = r.json()
                    return f"Notion page: {data.get('page_id') or 'ok'}"
            except Exception as e:
                return f"Notion failed: {e}"

        return f"Unknown tool: {name}"

    async def event_stream() -> AsyncIterator[bytes]:
        print(f"\nUser: {user_text}")
        # Announce model selection
        yield _format_sse({"type": "meta", "model": model})

        assistant_response = ""
        pending_tool_line: Optional[str] = None
        gmail_executed = False  # track if any gmail action executed to avoid NameError and duplicates

        # Try to extract intent and args directly from the user's message; this avoids relying on any hard-coded examples
        pre_intent = intent_to_tool(user_text)
        pre_executed = False
        if pre_intent:
            try:
                # If attempting to send without explicit account, downgrade to draft and ask user
                if pre_intent["name"] == "send_gmail" and not pre_intent["args"].get("account"):
                    pre_intent = {"name": "create_gmail_draft", "args": pre_intent["args"]}
                    yield _format_sse({"type": "token", "content": "\nℹ️ Missing sender account. Creating a draft instead. Please specify: from <your-email>."})
                yield _format_sse({"type": "token", "content": f"\n⚙️ Executing {pre_intent['name']}..."})
                result = await dispatch_tool(pre_intent["name"], pre_intent["args"])
                pre_executed = True
                yield _format_sse({"type": "token", "content": f"\n✅ {result}"})
            except Exception as e:
                yield _format_sse({"type": "token", "content": f"\n❌ Pre-dispatch failed: {e}"})

        try:
            # Ensure the system prompt teaches both draft and send variants
            # and explicitly shows account mapping for "from <email>" phrasing.
            async for chunk in _llm_router.ollama.chat_stream(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                system=system_prompt,
            ):
                # Normalize chunk text
                text_piece = ""
                if "message" in chunk and isinstance(chunk["message"], dict):
                    content = chunk["message"].get("content") or ""
                    text_piece = content
                elif "response" in chunk:
                    text_piece = chunk.get("response") or ""
                elif isinstance(chunk.get("content"), str):
                    text_piece = chunk["content"]

                if text_piece:
                    assistant_response += text_piece
                    # Emit token to UI, filtering think tags
                    if "<think>" not in text_piece and "</think>" not in text_piece:
                        yield _format_sse({"type": "token", "content": text_piece})

                    # Check if this piece (or accumulated) contains a full CALL_ line
                    lines = (pending_tool_line or "") + text_piece
                    # Try to find a complete single-line tool call
                    for maybe in lines.splitlines():
                        stripped = maybe.strip()
                        m = tool_call_pattern.match(stripped)
                        if m:
                            name = m.group("name")
                            args_text = m.group("args")
                            try:
                                args = parse_args(args_text)
                            except Exception as e:
                                yield _format_sse({"type": "token", "content": f"\n❌ Tool args error: {e}"})
                                continue
                            # Prevent accidental GET navigations in some clients by never echoing bare CALL_* back to UI as final-only content
                            # Execute the tool directly via server-side dispatch (POST), not by exposing a clickable URL.
                            if not (pre_executed and name.startswith("create_gmail_draft")):
                                yield _format_sse({"type": "token", "content": f"\n⚙️ Executing {name}..."})
                                result = await dispatch_tool(name, args)
                                yield _format_sse({"type": "token", "content": f"\n✅ {result}"})
                            pending_tool_line = None
                    # Preserve last line fragment in case tool-call spans chunks
                    if not text_piece.endswith("\n"):
                        pending_tool_line = (pending_tool_line or "") + text_piece
                    else:
                        pending_tool_line = None

                if chunk.get("done"):
                    break

            # After LLM stream ends, ensure we did not leave behind a pending CALL_ line that could be rendered by the client and trigger a GET
            if pending_tool_line:
                pending_tool_line = None
        except Exception as e:
            yield _format_sse({"type": "error", "error": str(e)})

        # Persist memory if requested
        if user_text and len(user_text.strip()) > 10:
            try:
                _id = await _memory.insert_with_embedding(
                    kind="interaction",
                    text=user_text,
                    meta={"thread_id": thread_id, "timestamp": asyncio.get_event_loop().time()},
                )
                if remember:
                    yield _format_sse({"type": "memory_saved", "id": _id})
            except Exception as e:
                if remember:
                    yield _format_sse({"type": "warn", "warning": f"memory_save_failed: {e}"})

        # Log final assistant text
        if assistant_response.strip():
            print(f"Richard: {assistant_response.strip()}")

        # End of stream marker compatible with SSE consumers
        yield b"data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
