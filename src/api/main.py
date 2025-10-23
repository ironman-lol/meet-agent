from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from typing import Optional, Dict, Any
import json
import os

from src.utils.chat_handler import ChatHandler
from src.models.gemini_transcript_processor import GeminiTranscriptProcessor
from src.integrations.calendar_integration import CalendarIntegration
from src.integrations.notion_integration import NotionIntegration
from src.utils.config import get_settings, Settings

app = FastAPI(
    title="Meet Agent",
    description="AI-powered meeting assistant",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load settings early
settings = get_settings()

# Initialize integrations
calendar_integration = CalendarIntegration()

notion_integration: Optional[NotionIntegration] = None
if getattr(settings, "NOTION_TOKEN", None):
    try:
        notion_integration = NotionIntegration(token=settings.NOTION_TOKEN)
    except Exception as e:
        # Initialization failure shouldn't kill the app; log and continue without Notion support
        print(f"Warning: NotionIntegration init failed: {e}")
        notion_integration = None

# Pass the notion_integration into ChatHandler so the agent can write when explicitly asked
chat_handler = ChatHandler(notion_integration=notion_integration)

templates = Jinja2Templates(directory="src/templates")


@app.get("/")
async def root(request: Request):
    """Render the chat interface."""
    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "messages": chat_handler.get_messages(),
            "has_transcript": chat_handler.current_analysis is not None
        }
    )


@app.post("/chat")
async def chat(request: Request, message: str = Form(...)):
    """Handle chat messages."""
    chat_handler.add_message(message, role="user")
    response = await chat_handler.get_response(message)
    chat_handler.add_message(response, role="assistant")
    return RedirectResponse(url="/", status_code=303)


@app.post("/process-transcript")
async def process_transcript(
    request: Request,
    transcript: UploadFile = File(...),
    settings: Settings = Depends(get_settings)
):
    """
    Process a meeting transcript and return comprehensive analysis.
    This endpoint does NOT auto-write to Notion. Notion writes are explicit via /create-notion-page or chatbot command.
    """
    try:
        content = await transcript.read()
        transcript_text = content.decode("utf-8")

        analysis = chat_handler.process_transcript(transcript_text)

        # Attach suggested meeting times if calendar integration is configured
        if analysis.get("meeting_requests") and getattr(settings, "GOOGLE_CLIENT_ID", None):
            for meeting in analysis["meeting_requests"]:
                proposed_time = meeting.get("proposed_time")
                suggested_times = calendar_integration.suggest_meeting_times(
                    target_date=proposed_time,
                    duration_minutes=meeting.get("duration_minutes", 60)
                )
                meeting["suggested_times"] = suggested_times

        return RedirectResponse(url="/", status_code=303)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/create-notion-page")
async def create_notion_page(
    content: Dict[str, Any],
    settings: Settings = Depends(get_settings)
):
    """
    Explicit endpoint to create a Notion page. Only available if NotionIntegration initialized.
    Expects JSON payload:
    {
      "title": "Meeting Title",
      "summary": "Short summary",
      "action_items": [...],
      // optional: parent_type "database" or "page" and parent_id if you want to override config
      "parent_type": "database" | "page",
      "parent_id": "..."
    }
    """
    if not notion_integration:
        raise HTTPException(status_code=500, detail="Notion integration not configured")

    try:
        title = content.get("title", "Meeting Notes")
        summary = content.get("summary", "")
        action_items = content.get("action_items", [])
        parent_type = content.get("parent_type") or ("database" if getattr(settings, "NOTION_DATABASE_ID", None) else "page")
        parent_id = content.get("parent_id") or (getattr(settings, "NOTION_DATABASE_ID", None) or getattr(settings, "NOTION_PARENT_PAGE_ID", None))

        page_id = notion_integration.create_meeting_page(
            title=title,
            summary=summary,
            action_items=action_items,
            parent_id=parent_id,
            parent_type=parent_type
        )
        return {"message": "Notion page created successfully", "page_id": page_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/schedule-meeting")
async def schedule_meeting(
    meeting_details: Dict[str, Any],
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
            "event_id": event.get("id"),
            "event_link": event.get("htmlLink")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
