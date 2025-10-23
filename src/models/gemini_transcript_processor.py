import google.generativeai as genai
from datetime import datetime
from typing import Dict, List
import re
import json
from src.utils.config import get_settings

settings = get_settings()

class GeminiTranscriptProcessor:
    def __init__(self):
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        self.model = genai.GenerativeModel('gemini-pro')
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
                
            time_match = re.search(self.time_pattern, line)
            speaker_match = re.search(self.speaker_pattern, line)
            
            if time_match and speaker_match:
                timestamp = time_match.group(1)
                speaker = speaker_match.group(1).split(']')[1].strip()
                content = speaker_match.group(2).strip()
                
                messages.append({
                    "timestamp": timestamp,
                    "speaker": speaker,
                    "content": content
                })
        
        return messages

    def generate_summary(self, messages: List[Dict]) -> Dict:
        """
        Generate an AI-powered summary of the meeting using Gemini.
        """
        conversation = "\n".join([f"{msg['speaker']}: {msg['content']}" for msg in messages])
        
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