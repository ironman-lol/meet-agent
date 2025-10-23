import google.generativeai as genai
from datetime import datetime
from typing import Dict, List
import re
import json
import os
from src.utils.config import get_settings

settings = get_settings()

class GeminiTranscriptProcessor:
    def __init__(self):
        # Check for API key
        api_key = settings.GOOGLE_API_KEY
        if not api_key or api_key == "your_google_api_key_here":
            raise ValueError("Please set a valid Google API key in the .env file")
            
        genai.configure(api_key=api_key)

        # Check for manually specified model
        selected_model = os.getenv("SELECTED_MODEL")
        if selected_model:
            print(f"Using manually specified model: {selected_model}")
            self.model = genai.GenerativeModel(selected_model)
            return

        # List and analyze available models
        available_models = list(genai.list_models())  # Convert generator to list
        print("Available models count:", len(available_models))

        def is_text_gen_model(m):
            # get supported_generation_methods field (exists on Model)
            methods = None
            try:
                methods = getattr(m, "supported_generation_methods", None)
                if methods is None and isinstance(m, dict):
                    methods = m.get("supported_generation_methods")
            except Exception:
                methods = None

            # normalize to list of lowercase strings
            if not methods:
                return False
            methods_lc = [str(x).lower() for x in methods]

            # exclude embed-only / image-only / predict-only markers
            if any(x in methods_lc for x in ("embedcontent","embed","predict")):
                return False

            # accept if it supports any known generation method
            accept_markers = ("generatecontent", "bidigeneratecontent", "createcachedcontent", "batchgeneratecontent", "generateanswer")
            return any(mk in methods_lc for mk in accept_markers)

        # collect candidates and ensure we have a list
        try:
            text_models = [m for m in available_models if is_text_gen_model(m)]
        except TypeError:  # If available_models is still a generator somehow
            available_models = list(available_models)
            text_models = [m for m in available_models if is_text_gen_model(m)]

        if not text_models:
            # dump signatures for debugging
            print("\nDumping all available models for debugging:")
            for m in available_models:
                try:
                    sig = {
                        "name": getattr(m, "name", None),
                        "display_name": getattr(m, "display_name", None),
                        "supported_generation_methods": getattr(m, "supported_generation_methods", None)
                    }
                    print(f"MODEL SIGNATURE: {sig}")
                    print(f"Raw supported_generation_methods: {getattr(m, 'supported_generation_methods', None)}")
                except Exception as e:
                    print(f"MODEL RAW ({type(m)}): {repr(m)}")
                    print(f"Error getting signature: {str(e)}")
            raise RuntimeError("No text generation models found. See signatures above.")

        # prefer Gemini by name, else pick first
        def name_of(m):
            return getattr(m, "name", None) or (m.get("name") if isinstance(m, dict) else None)

        gemini = [m for m in text_models if "gemini" in (name_of(m) or "").lower()]
        chosen = gemini[0] if gemini else text_models[0]
        model_name = name_of(chosen)
        print("Selected model:", model_name)

        # instantiate generative model (use name/id as SDK expects)
        self.model = genai.GenerativeModel(model_name)

        # conservative verification: try multiple call patterns
        test_prompt = "Say: hello"
        test_response = None
        errors = []

        # try model.generate_content (SDK usually exposes snake_case)
        try:
            fn = getattr(self.model, "generate_content", None)
            if callable(fn):
                test_response = fn(test_prompt)
        except Exception as e:
            errors.append(("generate_content", str(e)))

        # try bidiGenerate variant if available on model (some models are bidi)
        if not test_response:
            try:
                fn = getattr(self.model, "bidi_generate_content", None) or getattr(self.model, "bidiGenerateContent", None)
                if callable(fn):
                    test_response = fn(test_prompt)
            except Exception as e:
                errors.append(("bidi_generate", str(e)))

        # try top-level helper if present (alternative SDK helper)
        if not test_response:
            try:
                # genai.generate_text signature may vary; adapt if your SDK exposes it
                if hasattr(genai, "generate_text"):
                    test_response = genai.generate_text(model=model_name, input=test_prompt)
            except Exception as e:
                errors.append(("genai.generate_text", str(e)))

        # validate shape
        if not test_response:
            print("Model verification failed. Attempted calls:", errors)
            raise RuntimeError("Model verification failed; check SDK method names and that the API key has text-gen access.")

        # if response object uses .text or content field, adapt when parsing later
        print("Model verification succeeded. Response repr:", repr(test_response))
        
        # Model initialization is handled in the try-except block above
            
        self.time_pattern = r'\[(\d{2}:\d{2}:\d{2})\]'
        self.speaker_pattern = r'\[(.*?)\].*?:(.*)'

    def process_transcript(self, transcript: str) -> Dict:
        """
        Process the entire transcript and return comprehensive analysis.
        """
        messages = self.extract_messages(transcript)
        
        # Get AI-powered analysis
        summary = self.generate_summary(messages)
        action_items = self.extract_action_items(messages)
        meeting_requests = self.extract_meeting_requests(messages)
        key_decisions = self.extract_key_decisions(messages)
        
        return {
            "summary": summary,
            "action_items": action_items,
            "meeting_requests": meeting_requests,
            "key_decisions": key_decisions,
            "participants": list(set(msg["speaker"] for msg in messages)),
            "duration": self._calculate_duration(messages)
        }

    def extract_messages(self, transcript: str) -> List[Dict]:
        """
        Extract messages from the transcript with timestamp and speaker information.
        """
        messages = []
        for line in transcript.split('\n'):
            if not line.strip():
                continue
                
            # Extract timestamp - pattern: [HH:MM:SS]
            time_match = re.search(r'\[(\d{2}:\d{2}:\d{2})\]', line)
            if not time_match:
                continue
                
            timestamp = time_match.group(1)
            
            # Remove timestamp from line and extract speaker and content
            remaining_text = line[line.find(']') + 1:].strip()
            if ':' not in remaining_text:
                continue
                
            speaker, content = remaining_text.split(':', 1)
            
            messages.append({
                "timestamp": timestamp,
                "speaker": speaker.strip(),
                "content": content.strip()
            })
        
        return messages

    def generate_summary(self, messages: List[Dict]) -> Dict:
        """
        Generate an AI-powered summary of the meeting.
        """
        print("Generating meeting summary...")
        conversation = "\n".join([f"{msg['speaker']}: {msg['content']}" for msg in messages])
        print(f"Prepared conversation text: {len(conversation)} characters")
        
        prompt = """
        Analyze the following meeting transcript and provide:
        1. A concise summary (2-3 paragraphs)
        2. List of main topics discussed
        3. Key points highlighted
        
        Format your response as a JSON object with these keys:
        {
            "summary": "your summary here",
            "main_topics": ["topic 1", "topic 2", ...],
            "key_points": ["point 1", "point 2", ...]
        }

        Meeting Transcript:
        """ + conversation

        response = self.model.generate_content(prompt)
        # Extract JSON from response
        try:
            json_str = response.text[response.text.find('{'):response.text.rfind('}')+1]
            return json.loads(json_str)
        except:
            # Fallback structure if JSON parsing fails
            return {
                "summary": response.text,
                "main_topics": [],
                "key_points": []
            }

    def extract_action_items(self, messages: List[Dict]) -> List[Dict]:
        """
        Extract action items using Gemini.
        """
        conversation = "\n".join([f"{msg['speaker']}: {msg['content']}" for msg in messages])
        
        prompt = """
        Analyze this meeting transcript and identify all action items. For each action item, provide:
        1. Who is responsible
        2. What needs to be done
        3. Any mentioned deadlines

        Format your response as a JSON array of objects:
        [
            {
                "assignee": "person name",
                "task": "what needs to be done",
                "deadline": "mentioned deadline or null",
                "context": "relevant context"
            }
        ]

        Meeting Transcript:
        """ + conversation

        response = self.model.generate_content(prompt)
        try:
            json_str = response.text[response.text.find('['):response.text.rfind(']')+1]
            return json.loads(json_str)
        except:
            return []

    def extract_meeting_requests(self, messages: List[Dict]) -> List[Dict]:
        """
        Extract meeting requests using Gemini.
        """
        conversation = "\n".join([f"{msg['speaker']}: {msg['content']}" for msg in messages])
        
        prompt = """
        Analyze this conversation for any mentions of future meetings or scheduling requests.
        For each meeting request, identify:
        1. Who requested the meeting
        2. Proposed time/date
        3. Suggested participants
        4. Meeting purpose

        Format your response as a JSON array of objects:
        [
            {
                "requester": "person name",
                "proposed_time": "mentioned time",
                "participants": ["person1", "person2"],
                "purpose": "meeting purpose"
            }
        ]

        Meeting Transcript:
        """ + conversation

        response = self.model.generate_content(prompt)
        try:
            json_str = response.text[response.text.find('['):response.text.rfind(']')+1]
            return json.loads(json_str)
        except:
            return []

    def extract_key_decisions(self, messages: List[Dict]) -> List[Dict]:
        """
        Extract key decisions using Gemini.
        """
        conversation = "\n".join([f"{msg['speaker']}: {msg['content']}" for msg in messages])
        
        prompt = """
        Analyze this conversation and identify key decisions made during the meeting.
        For each decision, provide:
        1. What was decided
        2. Who made or approved the decision
        3. Any context or rationale provided

        Format your response as a JSON array of objects:
        [
            {
                "decision": "what was decided",
                "decision_maker": "who made the decision",
                "rationale": "context or reasoning"
            }
        ]

        Meeting Transcript:
        """ + conversation

        response = self.model.generate_content(prompt)
        try:
            json_str = response.text[response.text.find('['):response.text.rfind(']')+1]
            return json.loads(json_str)
        except:
            return []

    def _calculate_duration(self, messages: List[Dict]) -> str:
        """
        Calculate the duration of the meeting.
        """
        if not messages:
            return "0:00"
            
        start = datetime.strptime(messages[0]["timestamp"], "%H:%M:%S")
        end = datetime.strptime(messages[-1]["timestamp"], "%H:%M:%S")
        duration = end - start
        
        return str(duration)