from notion_client import Client
from typing import Dict, List, Optional
import os

class NotionIntegration:
    def __init__(self, token: str = None):
        self.token = token or os.getenv('NOTION_TOKEN')
        self.client = Client(auth=self.token)

    def create_meeting_page(self, 
                          title: str,
                          summary: str,
                          action_items: List[Dict],
                          parent_page_id: str) -> str:
        """
        Create a new Notion page for meeting notes.
        """
        # Format action items as a bulleted list
        action_items_content = []
        for item in action_items:
            action_items_content.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{
                        "type": "text",
                        "text": {
                            "content": f"{item['speaker']}: {item['action']}"
                        }
                    }]
                }
            })

        # Create the page
        page = self.client.pages.create(
            parent={"page_id": parent_page_id},
            properties={
                "title": {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                }
            },
            children=[
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "Meeting Summary"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": summary}}]
                    }
                },
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "Action Items"}}]
                    }
                },
                *action_items_content
            ]
        )

        return page["id"]

    def create_task(self, 
                   task_description: str,
                   assignee: Optional[str] = None,
                   due_date: Optional[str] = None,
                   database_id: str = None) -> str:
        """
        Create a new task in a Notion database.
        """
        properties = {
            "Name": {
                "title": [
                    {
                        "text": {
                            "content": task_description
                        }
                    }
                ]
            },
            "Status": {
                "select": {
                    "name": "Not Started"
                }
            }
        }

        if assignee:
            properties["Assignee"] = {
                "rich_text": [
                    {
                        "text": {
                            "content": assignee
                        }
                    }
                ]
            }

        if due_date:
            properties["Due Date"] = {
                "date": {
                    "start": due_date
                }
            }

        task = self.client.pages.create(
            parent={"database_id": database_id},
            properties=properties
        )

        return task["id"]

    def update_task_status(self, task_id: str, status: str):
        """
        Update the status of a task.
        """
        self.client.pages.update(
            page_id=task_id,
            properties={
                "Status": {
                    "select": {
                        "name": status
                    }
                }
            }
        )

    def get_tasks(self, database_id: str, filter_params: Optional[Dict] = None) -> List[Dict]:
        """
        Get tasks from a Notion database with optional filtering.
        """
        response = self.client.databases.query(
            database_id=database_id,
            filter=filter_params
        )
        
        return response["results"]