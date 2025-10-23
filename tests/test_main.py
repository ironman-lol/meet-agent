import pytest
from fastapi.testclient import TestClient
from datetime import datetime
import json

from src.api.main import app
from src.models.gemini_transcript_processor import GeminiTranscriptProcessor
from src.integrations.calendar_integration import CalendarIntegration
from src.integrations.notion_integration import NotionIntegration

client = TestClient(app)

# Sample test data
SAMPLE_TRANSCRIPT = """
[00:00:00] John: Let's discuss the project timeline.
[00:00:15] Sarah: We need to complete the first phase by next Friday.
[00:00:30] John: I'll schedule a follow-up meeting for next Tuesday at 2 PM.
[00:00:45] Mike: I'll prepare the documentation by Thursday.
"""

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_transcript_processor():
    processor = GeminiTranscriptProcessor()
    messages = processor.extract_messages(SAMPLE_TRANSCRIPT)
    
    assert len(messages) == 4
    assert messages[0]["speaker"] == "John"
    assert "project timeline" in messages[0]["content"]

def test_calendar_integration():
    calendar = CalendarIntegration()
    start_time = datetime.now()
    
    # Test availability check
    is_available = calendar.check_availability(start_time)
    assert isinstance(is_available, bool)
    
    # Test meeting time suggestions
    suggestions = calendar.suggest_meeting_times(start_time)
    assert isinstance(suggestions, list)

def test_notion_integration():
    notion = NotionIntegration()
    
    # Test task creation format
    task_description = "Complete documentation"
    assignee = "Mike"
    due_date = "2023-12-31"
    
    # This should raise an error without proper credentials
    with pytest.raises(Exception):
        notion.create_task(
            task_description=task_description,
            assignee=assignee,
            due_date=due_date
        )

def test_process_transcript_endpoint():
    # Create a test file-like object
    test_file = ('transcript.txt', SAMPLE_TRANSCRIPT)
    
    response = client.post(
        "/process-transcript",
        files={"transcript": test_file}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data