from typing import List, Dict, Optional, Any
from src.models.gemini_transcript_processor import GeminiTranscriptProcessor
import google.generativeai as genai
from src.utils.config import get_settings
import os
import json

settings = get_settings()

# Hardcoded model name as before
MODEL_NAME = "gemini-2.5-flash-lite"

class ChatHandler:
    def __init__(self, notion_integration: Optional[Any] = None):
        print("Initializing ChatHandler...")
        self.messages: List[Dict[str, str]] = []
        self.current_transcript: Optional[str] = None
        self.current_analysis: Optional[Dict[str, Any]] = None

        # Notion integration (optional tool)
        self.notion = notion_integration

        # Configure API key for Gemini usage (existing behavior retained)
        api_key = settings.GOOGLE_API_KEY
        if not api_key or api_key == "your_google_api_key_here":
            raise ValueError("Please set a valid Google API key in the .env file")
        genai.configure(api_key=api_key)

        # instantiate model wrapper if SDK supports it
        try:
            self.model = genai.GenerativeModel(MODEL_NAME)
        except Exception:
            self.model = None
        self.model_name = MODEL_NAME

        # initialize transcript processor
        self.transcript_processor = GeminiTranscriptProcessor()

        # optional: load sample transcript if available (kept short)
        sample_path = "/workspaces/meet-agent/sample_transcript1.txt"
        if os.path.exists(sample_path):
            try:
                with open(sample_path, "r", encoding="utf-8") as f:
                    sample_transcript = f.read()
                self.process_transcript(sample_transcript)
                self.add_message("Transcript loaded and processed.", role="assistant")
            except Exception as e:
                print(f"Failed to load/process sample transcript: {e}")
                self.add_message("Ready. Failed to auto-load sample transcript.", role="assistant")
        else:
            self.add_message("Ready to analyze transcripts.", role="assistant")

    def add_message(self, content: str, role: str = "user"):
        self.messages.append({"role": role, "content": content})

    def get_messages(self) -> List[Dict[str, str]]:
        return self.messages

    def _call_model(self, prompt: str) -> str:
        # minimal robust caller (same as before)
        if self.model:
            for method in ("generate_content", "generate_text", "create_text", "generate"):
                fn = getattr(self.model, method, None)
                if callable(fn):
                    try:
                        resp = fn(prompt)
                        if hasattr(resp, "text"):
                            return resp.text
                        if hasattr(resp, "content"):
                            return resp.content
                        if isinstance(resp, dict):
                            for k in ("content", "text", "output"):
                                if k in resp:
                                    return resp[k]
                            return json.dumps(resp)
                        if isinstance(resp, str):
                            return resp
                    except Exception:
                        pass
        for helper in ("generate_text", "generate", "create_text"):
            fn = getattr(genai, helper, None)
            if callable(fn):
                try:
                    resp = fn(model=self.model_name, input=prompt)
                    if hasattr(resp, "text"):
                        return resp.text
                    if isinstance(resp, dict):
                        for k in ("content", "text", "output"):
                            if k in resp:
                                return resp[k]
                        return json.dumps(resp)
                    if isinstance(resp, str):
                        return resp
                except Exception:
                    pass
        return ""

    def process_transcript(self, transcript_text: str) -> Dict[str, Any]:
        try:
            self.current_transcript = transcript_text
            self.current_analysis = self.transcript_processor.process_transcript(transcript_text)
            # add a short assistant message
            summary_text = ""
            if isinstance(self.current_analysis, dict) and "summary" in self.current_analysis:
                summary = self.current_analysis["summary"]
                summary_text = summary.get("summary") if isinstance(summary, dict) else str(summary)
            self.add_message("Transcript processed. Summary available.", role="assistant")
            return self.current_analysis or {}
        except Exception as e:
            print(f"Error processing transcript: {e}")
            self.add_message(f"Error processing transcript: {e}", role="assistant")
            return {}

    async def get_response(self, user_message: str) -> str:
        """
        Generate a reply. If user explicitly requests a Notion write, execute it using the notion tool.
        """
        if not self.current_analysis:
            return "Please upload or provide a transcript first."

        text = user_message.lower().strip()

        # Detect explicit Notion-write intent (explicit phrases only)
        notion_triggers = [
            "save to notion",
            "write to notion",
            "create notion page",
            "export to notion",
            "store to notion",
            "save notes to notion",
            "please save to notion",
            "please write to notion",
            "create a notion page",
            "save meeting to notion"
        ]
        if any(trigger in text for trigger in notion_triggers):
            if not self.notion:
                return "Notion integration is not configured. Set NOTION_TOKEN and initialize NotionIntegration."
            # Build content for Notion
            title = None
            # try to extract a title from the user message like "create notion page titled X"
            # simple heuristic:
            if "title" in text or "titled" in text:
                # naive extraction: split on 'titled' or 'title' and take rest
                for sep in ("titled", "title"):
                    if sep in text:
                        parts = text.split(sep, 1)
                        if len(parts) > 1 and parts[1].strip():
                            title = parts[1].strip().strip(' "\'')
                            break
            # fallbacks
            if not title:
                title = f"Meeting Notes - auto ({self.current_transcript[:30].splitlines()[0] if self.current_transcript else 'untitled'})"

            # summary and action items from analysis
            summary_obj = self.current_analysis.get("summary", {})
            if isinstance(summary_obj, dict):
                summary_text = summary_obj.get("summary", "")
            else:
                summary_text = str(summary_obj)
            action_items = self.current_analysis.get("action_items", [])

            # call Notion (synchronous). create_meeting_page supports parent selection as implemented earlier.
            try:
                parent_id = getattr(settings, "NOTION_DATABASE_ID", None) or getattr(settings, "NOTION_PARENT_PAGE_ID", None)
                parent_type = "database" if getattr(settings, "NOTION_DATABASE_ID", None) else "page"
                page_id = self.notion.create_meeting_page(
                    title=title,
                    summary=summary_text,
                    action_items=action_items,
                    parent_id=parent_id,
                    parent_type=parent_type
                )
                # add assistant message to messages and return confirmation
                confirmation = f"Saved to Notion: page id {page_id}"
                self.add_message(confirmation, role="assistant")
                return confirmation
            except Exception as e:
                err = f"Failed to write to Notion: {e}"
                self.add_message(err, role="assistant")
                return err

        # If not a Notion intent, proceed with normal conversational behavior (same compact prompts)
        user_lower = user_message.lower()
        context = {
            "summary": self.current_analysis.get("summary"),
            "action_items": self.current_analysis.get("action_items"),
            "meeting_requests": self.current_analysis.get("meeting_requests"),
            "key_decisions": self.current_analysis.get("key_decisions"),
        }

        # intent-driven prompts (concise)
        if any(k in user_lower for k in ("schedule", "meeting", "calendar", "when")):
            prompt = (
                f"Using meeting requests:\n{json.dumps(context['meeting_requests'])}\n\nUser: {user_message}\n"
                "Return a concise scheduling suggestion with purpose, attendees and proposed time/date."
            )
        elif any(k in user_lower for k in ("task", "action", "todo", "assignment")):
            prompt = (
                f"Using action items:\n{json.dumps(context['action_items'])}\n\nUser: {user_message}\n"
                "Return a concise list of tasks with assignees and deadlines."
            )
        elif any(k in user_lower for k in ("decide", "decision", "agreed", "conclusion")):
            prompt = (
                f"Using key decisions:\n{json.dumps(context['key_decisions'])}\n\nUser: {user_message}\n"
                "Return a concise explanation of decisions and rationale."
            )
        else:
            prompt = (
                "Based on the analysis below, answer concisely.\n\n"
                f"Summary: {json.dumps(context['summary'])}\n"
                f"Action Items: {json.dumps(context['action_items'])}\n"
                f"Meeting Requests: {json.dumps(context['meeting_requests'])}\n"
                f"Key Decisions: {json.dumps(context['key_decisions'])}\n\n"
                f"User: {user_message}\n\nRespond concisely."
            )

        raw = self._call_model(prompt)
        if not raw:
            return "No response from model. Check API key, quota or model availability."
        # add assistant message to history
        self.add_message(raw.strip(), role="assistant")
        return raw.strip()

    def clear_conversation(self):
        self.messages = []
        self.current_transcript = None
        self.current_analysis = None
