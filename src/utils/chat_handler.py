from typing import List, Dict, Optional
from src.models.gemini_transcript_processor import GeminiTranscriptProcessor
import google.generativeai as genai
from src.utils.config import get_settings

settings = get_settings()

class ChatHandler:
    def __init__(self):
        print("Initializing ChatHandler...")
        # Initialize basic properties first
        self.messages: List[Dict[str, str]] = []
        self.current_transcript = None
        self.current_analysis = None
        
        try:
            genai.configure(api_key=settings.GOOGLE_API_KEY)
            self.model = genai.GenerativeModel('gemini-pro')
            print("Gemini model initialized")
            
            self.transcript_processor = GeminiTranscriptProcessor()
            print("Transcript processor initialized")
            
            # Load and process sample transcript automatically
            print("Loading sample transcript...")
            with open('/workspaces/meet-agent/sample_transcript1.txt', 'r') as f:
                sample_transcript = f.read()
                print(f"Sample transcript loaded: {len(sample_transcript)} characters")
                self.process_transcript(sample_transcript)
                
                # Add initial welcome message
                welcome_msg = (
                    "👋 Welcome! I've analyzed the technical architecture meeting transcript. Here are the key points:\n\n"
                    f"📝 {self.current_analysis['summary']['summary']}\n\n"
                    "I can help you with:\n"
                    "1. 📅 Scheduling follow-up meetings mentioned\n"
                    "2. 📋 Creating Notion pages for tasks and decisions\n"
                    "3. 🔍 Answering questions about specific topics\n"
                    "4. 📊 Providing more details about any discussion point\n\n"
                    "What would you like to know more about?"
                )
                self.add_message(welcome_msg, role="assistant")
        except Exception as e:
            print(f"Error initializing ChatHandler: {str(e)}")
            self.add_message(
                "👋 Welcome! I'm ready to help you analyze meeting transcripts. "
                "There was an issue loading the sample transcript, but you can ask me questions "
                "once a transcript is processed.",
                role="assistant"
            )

    def add_message(self, content: str, role: str = "user"):
        """Add a message to the conversation history."""
        self.messages.append({"role": role, "content": content})

    def get_messages(self) -> List[Dict[str, str]]:
        """Get all messages in the conversation."""
        return self.messages

    def process_transcript(self, transcript_text: str) -> Dict:
        """Process a transcript and store the analysis."""
        try:
            print(f"Processing transcript of length: {len(transcript_text)}")
            self.current_transcript = transcript_text
            print("Starting transcript analysis...")
            self.current_analysis = self.transcript_processor.process_transcript(transcript_text)
            print("Transcript analysis completed")
            
            # Add a summary message to the chat
            if isinstance(self.current_analysis, dict) and 'summary' in self.current_analysis:
                summary = (
                    "📄 I've analyzed the transcript. Here's a summary:\n\n"
                    f"{self.current_analysis['summary']['summary']}\n\n"
                    "You can ask me about:\n"
                    "- Action items\n"
                    "- Meeting requests\n"
                    "- Key decisions\n"
                    "- Specific topics discussed"
                )
            else:
                summary = "I've processed the transcript but encountered an issue generating the summary. You can still ask me questions about the content."
            
            self.add_message(summary, role="assistant")
            return self.current_analysis
        except Exception as e:
            error_msg = f"Error processing transcript: {str(e)}"
            print(error_msg)
            self.add_message(
                "I encountered an error while processing the transcript.\n\n"
                f"Error details: {str(e)}\n\n"
                "Please make sure:\n"
                "1. The transcript follows the format: [HH:MM:SS] Speaker: Message\n"
                "2. The Google API key is properly configured\n"
                "3. The transcript file is accessible",
                role="assistant"
            )
            return {}

    async def get_response(self, user_message: str) -> str:
        """Get a response to a user message."""
        if not self.current_analysis:
            return "Please upload a transcript first so I can help you better."

        # Create a context-aware prompt based on common user intents
        if any(word in user_message.lower() for word in ['schedule', 'meeting', 'calendar', 'when']):
            prompt = f"""
            Based on the meeting transcript where:
            Meeting Requests: {self.current_analysis['meeting_requests']}
            
            The user asks: {user_message}
            
            If there are relevant meeting requests, suggest scheduling them and provide details.
            Format the response in a friendly way, including:
            1. The purpose of the meeting
            2. Suggested attendees
            3. Proposed time/date
            4. Any context from the discussion
            
            If you suggest scheduling, end with: "Would you like me to schedule this meeting?"
            """
        elif any(word in user_message.lower() for word in ['task', 'action', 'todo', 'assignment']):
            prompt = f"""
            Based on the meeting transcript where:
            Action Items: {self.current_analysis['action_items']}
            
            The user asks: {user_message}
            
            List relevant action items, including:
            1. Who is responsible
            2. What needs to be done
            3. Any deadlines mentioned
            4. Related context
            
            If there are tasks to track, end with: "Would you like me to create a Notion page to track these tasks?"
            """
        elif any(word in user_message.lower() for word in ['decide', 'decision', 'agreed', 'conclusion']):
            prompt = f"""
            Based on the meeting transcript where:
            Key Decisions: {self.current_analysis['key_decisions']}
            
            The user asks: {user_message}
            
            Explain the relevant decisions, including:
            1. What was decided
            2. Who made/approved the decision
            3. The rationale behind it
            4. Any implementation details discussed
            
            If there are important decisions, end with: "Would you like me to document these decisions in Notion?"
            """
        else:
            prompt = f"""
            Based on the meeting transcript analysis, where:
            - Summary: {self.current_analysis['summary']}
            - Action Items: {self.current_analysis['action_items']}
            - Meeting Requests: {self.current_analysis['meeting_requests']}
            - Key Decisions: {self.current_analysis['key_decisions']}

            User Question: {user_message}

            Provide a helpful and relevant response using the information from the transcript analysis.
            If the user asks about something not covered in the transcript, politely indicate that.
            Format the response in a clear, conversational way.
            
            If your response involves actionable items, suggest relevant next steps (like scheduling meetings or creating Notion pages).
            """

        response = self.model.generate_content(prompt)
        return response.text

    def clear_conversation(self):
        """Clear the conversation history."""
        self.messages = []
        self.current_transcript = None
        self.current_analysis = None