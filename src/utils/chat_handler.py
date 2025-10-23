from typing import List, Dict, Optional, Any
from src.models.gemini_transcript_processor import GeminiTranscriptProcessor
import google.generativeai as genai
from src.utils.config import get_settings
import os
import json

settings = get_settings()

# Hardcode the low-cost text model
MODEL_NAME = "gemini-2.5-flash-lite"

class ChatHandler:
    def __init__(self):
        print("Initializing ChatHandler...")
        self.messages: List[Dict[str, str]] = []
        self.current_transcript: Optional[str] = None
        self.current_analysis: Optional[Dict[str, Any]] = None

        # Configure API key
        api_key = settings.GOOGLE_API_KEY
        if not api_key or api_key == "your_google_api_key_here":
            raise ValueError("Please set a valid Google API key in the .env file")
        genai.configure(api_key=api_key)

        # Instantiate model wrapper if SDK supports it; otherwise keep model_name and use top-level helpers.
        try:
            self.model = genai.GenerativeModel(MODEL_NAME)
        except Exception:
            self.model = None
        self.model_name = MODEL_NAME

        # Initialize transcript processor (kept unchanged)
        self.transcript_processor = GeminiTranscriptProcessor()

        # Try to load and automatically process sample transcript if it exists
        sample_path = "/workspaces/meet-agent/sample_transcript1.txt"
        if os.path.exists(sample_path):
            try:
                with open(sample_path, "r", encoding="utf-8") as f:
                    sample_transcript = f.read()
                print(f"Sample transcript loaded: {len(sample_transcript)} characters")
                self.process_transcript(sample_transcript)
                welcome_msg = (
                    "Welcome. Transcript processed. Ask about summary, action items, meeting requests, or key decisions."
                )
                self.add_message(welcome_msg, role="assistant")
            except Exception as e:
                print(f"Failed to load/process sample transcript: {e}")
                self.add_message(
                    "Welcome. Ready to analyze transcripts. Failed to auto-load sample transcript.",
                    role="assistant"
                )
        else:
            self.add_message("Welcome. Ready to analyze transcripts.", role="assistant")

    def add_message(self, content: str, role: str = "user"):
        self.messages.append({"role": role, "content": content})

    def get_messages(self) -> List[Dict[str, str]]:
        return self.messages

    def _call_model(self, prompt: str) -> str:
        """
        Minimal robust caller: prefer instance methods if available, then top-level helpers.
        Returns string (possibly empty) and never raises.
        """
        # Instance-level attempts
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
                        # swallow and try next
                        pass

        # Top-level helper fallback
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

        # Final fallback: empty string
        return ""

    def process_transcript(self, transcript_text: str) -> Dict[str, Any]:
        try:
            print(f"Processing transcript of length: {len(transcript_text)}")
            self.current_transcript = transcript_text
            self.current_analysis = self.transcript_processor.process_transcript(transcript_text)

            # Add concise assistant summary message
            if isinstance(self.current_analysis, dict) and "summary" in self.current_analysis:
                summary_text = self.current_analysis["summary"].get("summary") if isinstance(self.current_analysis["summary"], dict) else str(self.current_analysis["summary"])
                assistant_msg = (
                    "Transcript analyzed. Summary:\n\n" + (summary_text or "No summary generated.")
                )
            else:
                assistant_msg = "Transcript analyzed. Summary not available."

            self.add_message(assistant_msg, role="assistant")
            return self.current_analysis or {}
        except Exception as e:
            print(f"Error processing transcript: {e}")
            self.add_message(f"Error processing transcript: {e}", role="assistant")
            return {}

    async def get_response(self, user_message: str) -> str:
        if not self.current_analysis:
            return "Upload or provide a transcript first."

        user_lower = user_message.lower()
        # Build a compact context prompt
        context = {
            "summary": self.current_analysis.get("summary"),
            "action_items": self.current_analysis.get("action_items"),
            "meeting_requests": self.current_analysis.get("meeting_requests"),
            "key_decisions": self.current_analysis.get("key_decisions"),
        }
        # Choose intent-driven prompt templates
        if any(k in user_lower for k in ("schedule", "meeting", "calendar", "when")):
            prompt = (
                f"Using the meeting requests below, suggest scheduling details.\n\nMeeting Requests:\n{json.dumps(context['meeting_requests'])}\n\nUser question: {user_message}\n\n"
                "Return a concise suggestion with purpose, attendees, proposed time/date, and context."
            )
        elif any(k in user_lower for k in ("task", "action", "todo", "assignment")):
            prompt = (
                f"Using the action items below, list relevant tasks for the user.\n\nAction Items:\n{json.dumps(context['action_items'])}\n\nUser question: {user_message}\n\n"
                "Return a concise list of tasks with assignees and deadlines."
            )
        elif any(k in user_lower for k in ("decide", "decision", "agreed", "conclusion")):
            prompt = (
                f"Using the key decisions below, explain decisions relevant to the user.\n\nKey Decisions:\n{json.dumps(context['key_decisions'])}\n\nUser question: {user_message}\n\n"
                "Return a concise explanation of what was decided, who decided, and rationale."
            )
        else:
            prompt = (
                "Based on the following analysis, answer the user question concisely.\n\n"
                f"Summary: {json.dumps(context['summary'])}\n"
                f"Action Items: {json.dumps(context['action_items'])}\n"
                f"Meeting Requests: {json.dumps(context['meeting_requests'])}\n"
                f"Key Decisions: {json.dumps(context['key_decisions'])}\n\n"
                f"User question: {user_message}\n\nRespond concisely."
            )

        raw = self._call_model(prompt)
        # If model returned JSON, prefer extracting plain text; otherwise return raw
        if not raw:
            return "Model did not return a response. Check API key, quota, or model availability."
        return raw.strip()

    def clear_conversation(self):
        self.messages = []
        self.current_transcript = None
        self.current_analysis = None