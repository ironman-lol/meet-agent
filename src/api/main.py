from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict
import json

from src.models.gemini_transcript_processor import GeminiTranscriptProcessor
from src.integrations.calendar_integration import CalendarIntegration
from src.integrations.notion_integration import NotionIntegration
from src.utils.config import get_settings, Settings

app = FastAPI(
    title="Meet Agent",
    description="AI-powered meeting assistant using Google Gemini for transcript processing and task automation",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
transcript_processor = GeminiTranscriptProcessor()
calendar_integration = CalendarIntegration()
notion_integration = NotionIntegration()

@app.post("/process-transcript")
async def process_transcript(
    transcript: UploadFile = File(...),
    settings: Settings = Depends(get_settings)
):
    """
    Process a meeting transcript and return comprehensive analysis.
    """
    try:
        content = await transcript.read()
        transcript_text = content.decode("utf-8")
        
        # Process transcript
        analysis = transcript_processor.process_transcript(transcript_text)
        
        # Create Notion page with summary
        if settings.NOTION_TOKEN:
            notion_page_id = notion_integration.create_meeting_page(
                title=f"Meeting Summary - {transcript.filename}",
                summary=analysis["summary"]["summary"],
                action_items=analysis["action_items"],
                parent_page_id=settings.NOTION_DATABASE_ID
            )
            analysis["notion_page_id"] = notion_page_id
            
        # Process meeting requests
        if analysis["meeting_requests"] and settings.GOOGLE_CLIENT_ID:
            for meeting in analysis["meeting_requests"]:
                suggested_times = calendar_integration.suggest_meeting_times(
                    target_date=meeting["proposed_time"],
                    duration_minutes=60
                )
                meeting["suggested_times"] = suggested_times
        
        return analysis
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/schedule-meeting")
async def schedule_meeting(
    meeting_details: Dict,
    settings: Settings = Depends(get_settings)
):
    """
    Schedule a meeting based on extracted information or user request.
    """
    try:
        event = calendar_integration.create_meeting(
            title=meeting_details["title"],
            start_time=meeting_details["start_time"],
            duration_minutes=meeting_details.get("duration_minutes", 60),
            description=meeting_details.get("description", ""),
            attendees=meeting_details.get("attendees", [])
        )
        
        return {
            "message": "Meeting scheduled successfully",
            "event_id": event["id"],
            "event_link": event.get("htmlLink")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/create-notion-page")
async def create_notion_page(
    content: Dict,
    settings: Settings = Depends(get_settings)
):
    """
    Create a Notion page with meeting summary and action items.
    """
    try:
        page_id = notion_integration.create_meeting_page(
            title=content["title"],
            summary=content["summary"],
            action_items=content["action_items"],
            parent_page_id=settings.NOTION_DATABASE_ID
        )
        
        return {
            "message": "Notion page created successfully",
            "page_id": page_id
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """
    Simple health check endpoint.
    """
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)