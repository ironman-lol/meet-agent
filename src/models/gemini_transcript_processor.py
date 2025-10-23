import os
import re
import json
from datetime import datetime
from typing import Dict, List, Any
import google.generativeai as genai
from src.utils.config import get_settings

MODEL_NAME = "gemini-2.5-flash-lite"

settings = get_settings()

class GeminiTranscriptProcessor:
    """
    Minimal, pragmatic transcript processor that uses a hardcoded low-cost model.
    Removed model discovery, scoring, and startup verification to keep code direct.
    """

    def __init__(self):
        api_key = settings.GOOGLE_API_KEY
        if not api_key or api_key == "your_google_api_key_here":
            raise ValueError("Please set a valid Google API key in the .env file")

        genai.configure(api_key=api_key)
        # instantiate model object (SDK may accept name string or GenerativeModel wrapper)
        try:
            self.model = genai.GenerativeModel(MODEL_NAME)
        except Exception:
            # fallback: keep model name and call top-level helpers
            self.model = None

        self.model_name = MODEL_NAME
        self.time_pattern = r'\[(\d{2}:\d{2}:\d{2})\]'
        self.speaker_pattern = r'^\s*\[(\d{2}:\d{2}:\d{2})\]\s*(.*?):\s*(.*)$'

    # -------- transcript parsing --------
    def extract_messages(self, transcript: str) -> List[Dict[str, str]]:
        msgs: List[Dict[str, str]] = []
        for line in transcript.splitlines():
            if not line.strip():
                continue
            m = re.match(self.speaker_pattern, line)
            if m:
                ts, speaker, content = m.groups()
                msgs.append({"timestamp": ts, "speaker": speaker.strip(), "content": content.strip()})
                continue
            # fallback: find [HH:MM:SS] then split on first colon
            tmatch = re.search(self.time_pattern, line)
            if not tmatch:
                continue
            ts = tmatch.group(1)
            rest = line[line.find("]") + 1 :].strip()
            if ":" in rest:
                speaker, content = rest.split(":", 1)
                msgs.append({"timestamp": ts, "speaker": speaker.strip(), "content": content.strip()})
        return msgs

    # -------- model call helper (tries best-available call) --------
    def _call_model(self, prompt: str) -> str:
        # Prefer instance method if model wrapper exists
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
                        # don't raise here; try other options
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

        # Final fallback: return empty string (caller should handle)
        return ""

    # -------- extractors that ask the model --------
    def generate_summary(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        convo = "\n".join(f"{m['speaker']}: {m['content']}" for m in messages)
        prompt = (
            "Analyze the following meeting transcript and provide:\n"
            "1) A concise summary (2-3 paragraphs)\n"
            "2) A list of main topics\n"
            "3) Key points\n\n"
            "Return JSON object with keys: summary, main_topics, key_points\n\n"
            "Transcript:\n" + convo
        )
        raw = self._call_model(prompt)
        # try robust JSON extraction
        try:
            start = raw.find('{')
            end = raw.rfind('}')
            if start != -1 and end != -1 and end > start:
                return json.loads(raw[start:end+1])
        except Exception:
            pass
        return {"summary": raw.strip(), "main_topics": [], "key_points": []}

    def extract_action_items(self, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        convo = "\n".join(f"{m['speaker']}: {m['content']}" for m in messages)
        prompt = (
            "Find action items in this transcript. For each: assignee, task, deadline (or null), context.\n"
            "Return a JSON array of objects.\n\nTranscript:\n" + convo
        )
        raw = self._call_model(prompt)
        try:
            start = raw.find('[')
            end = raw.rfind(']')
            if start != -1 and end != -1 and end > start:
                return json.loads(raw[start:end+1])
        except Exception:
            pass
        return []

    def extract_meeting_requests(self, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        convo = "\n".join(f"{m['speaker']}: {m['content']}" for m in messages)
        prompt = (
            "List meeting/scheduling requests found. For each: requester, proposed_time, participants, purpose.\n"
            "Return JSON array.\n\nTranscript:\n" + convo
        )
        raw = self._call_model(prompt)
        try:
            start = raw.find('[')
            end = raw.rfind(']')
            if start != -1 and end != -1 and end > start:
                return json.loads(raw[start:end+1])
        except Exception:
            pass
        return []

    def extract_key_decisions(self, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        convo = "\n".join(f"{m['speaker']}: {m['content']}" for m in messages)
        prompt = (
            "Identify key decisions. For each: decision, decision_maker, rationale. Return JSON array.\n\nTranscript:\n" + convo
        )
        raw = self._call_model(prompt)
        try:
            start = raw.find('[')
            end = raw.rfind(']')
            if start != -1 and end != -1 and end > start:
                return json.loads(raw[start:end+1])
        except Exception:
            pass
        return []

    # -------- high-level processing --------
    def process_transcript(self, transcript: str) -> Dict[str, Any]:
        messages = self.extract_messages(transcript)
        return {
            "summary": self.generate_summary(messages),
            "action_items": self.extract_action_items(messages),
            "meeting_requests": self.extract_meeting_requests(messages),
            "key_decisions": self.extract_key_decisions(messages),
            "participants": sorted({m["speaker"] for m in messages}),
            "duration": self._calculate_duration(messages),
        }

    def _calculate_duration(self, messages: List[Dict[str, str]]) -> str:
        if not messages:
            return "0:00"
        try:
            start = datetime.strptime(messages[0]["timestamp"], "%H:%M:%S")
            end = datetime.strptime(messages[-1]["timestamp"], "%H:%M:%S")
            delta = end - start
            if delta.total_seconds() < 0:
                return "0:00"
            minutes = int(delta.total_seconds() // 60)
            seconds = int(delta.total_seconds() % 60)
            return f"{minutes}:{seconds:02d}"
        except Exception:
            return "0:00"