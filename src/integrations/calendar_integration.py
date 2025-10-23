from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import os
import pickle

class CalendarIntegration:
    def __init__(self):
        self.SCOPES = ['https://www.googleapis.com/auth/calendar']
        self.credentials = None
        self.service = None

    def authenticate(self):
        """
        Authenticate with Google Calendar API.
        """
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                self.credentials = pickle.load(token)

        if not self.credentials or not self.credentials.valid:
            if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                self.credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', self.SCOPES)
                self.credentials = flow.run_local_server(port=0)

            with open('token.pickle', 'wb') as token:
                pickle.dump(self.credentials, token)

        self.service = build('calendar', 'v3', credentials=self.credentials)

    def create_meeting(self, title: str, start_time: datetime, duration_minutes: int = 60,
                      description: str = "", attendees: list = None):
        """
        Create a calendar event for a meeting.
        """
        if not self.service:
            self.authenticate()

        end_time = start_time + timedelta(minutes=duration_minutes)

        event = {
            'summary': title,
            'description': description,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'UTC',
            },
        }

        if attendees:
            event['attendees'] = [{'email': email} for email in attendees]

        event = self.service.events().insert(calendarId='primary', body=event).execute()
        return event

    def check_availability(self, start_time: datetime, duration_minutes: int = 60):
        """
        Check if a time slot is available.
        """
        if not self.service:
            self.authenticate()

        end_time = start_time + timedelta(minutes=duration_minutes)
        
        # Get the events in the proposed time slot
        events_result = self.service.events().list(
            calendarId='primary',
            timeMin=start_time.isoformat() + 'Z',
            timeMax=end_time.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        return len(events) == 0  # True if no events found in the time slot

    def suggest_meeting_times(self, target_date: datetime, duration_minutes: int = 60,
                            start_hour: int = 9, end_hour: int = 17):
        """
        Suggest available meeting times for a given date.
        """
        if not self.service:
            self.authenticate()

        suggestions = []
        current_slot = target_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        end_time = target_date.replace(hour=end_hour, minute=0, second=0, microsecond=0)

        while current_slot < end_time:
            if self.check_availability(current_slot, duration_minutes):
                suggestions.append(current_slot)
            current_slot += timedelta(minutes=30)  # Check every 30 minutes

        return suggestions