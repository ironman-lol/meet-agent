from notion_client import Client
from typing import Dict, List, Optional, Any
import os

class NotionIntegration:
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("NOTION_TOKEN")
        if not self.token:
            raise ValueError("Notion token not provided (env: NOTION_TOKEN)")
        self.client = Client(auth=self.token)

    def _format_action_item_text(self, item: Dict[str, Any]) -> str:
        """
        Robustly format an action item from different possible shapes.
        Known shapes:
          - {"assignee": "Name", "task": "Do X", "deadline": "2025-01-01", "context": "..."}
          - {"speaker": "Name", "action": "Do X"}
        """
        parts = []
        assignee = item.get("assignee") or item.get("speaker") or item.get("owner")
        task = item.get("task") or item.get("action") or item.get("description") or ""
        deadline = item.get("deadline") or item.get("due") or ""
        if assignee:
            parts.append(f"{assignee}:")
        parts.append(task)
        if deadline:
            parts.append(f"(Due: {deadline})")
        context = item.get("context") or item.get("notes")
        if context:
            parts.append(f"- {context}")
        return " ".join(p for p in parts if p)

    def create_meeting_page(
        self,
        title: str,
        summary: str,
        action_items: Optional[List[Dict[str, Any]]] = None,
        parent_id: Optional[str] = None,
        parent_type: str = "page"  # "page" or "database"
    ) -> str:
        """
        Create a Notion page containing meeting summary and action items.
        parent_type:
          - "page": parent_id is a page_id and page will be created under that page
          - "database": parent_id is a database_id and a new row will be created (title prop required)
        Returns created page id.
        """
        action_items = action_items or []

        children_blocks = [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Meeting Summary"}}]}
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": summary or ""}}]}
            },
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Action Items"}}]}
            }
        ]

        for item in action_items:
            text = self._format_action_item_text(item)
            children_blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": text}}]
                }
            })

        # Build parent argument depending on parent_type
        if parent_type == "database":
            # Create a page (row) inside a database: parent needs database_id and properties must match DB schema
            # Minimal approach: create a title property called "Name"
            properties = {
                "Name": {
                    "title": [{"type": "text", "text": {"content": title}}]
                }
            }
            page = self.client.pages.create(
                parent={"database_id": parent_id},
                properties=properties,
                children=children_blocks
            )
        else:
            # parent_type == "page" (default): create a standalone page under another page
            page = self.client.pages.create(
                parent={"page_id": parent_id} if parent_id else {"workspace": True},
                properties={
                    "title": {
                        "title": [{"type": "text", "text": {"content": title}}]
                    }
                },
                children=children_blocks
            )

        return page.get("id") or page.get("url") or ""

    def add_key_decisions(self, page_id: str, decisions: List[str]) -> None:
        """
        Append a "Key Decisions" section to an existing page (page_id is a block or page id).
        """
        if not decisions:
            return

        children = [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Key Decisions"}}]}
            }
        ]
        for d in decisions:
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": d}}]
                }
            })

        # Append blocks to the given block/page
        self.client.blocks.children.append(block_id=page_id, children=children)

    def create_task(
        self,
        task_description: str,
        assignee: Optional[str] = None,
        due_date: Optional[str] = None,
        database_id: Optional[str] = None
    ) -> str:
        """
        Create a task in a Notion database. database_id is required.
        Returns the created page id.
        """
        if not database_id:
            raise ValueError("database_id is required to create a task in Notion")

        properties: Dict[str, Any] = {
            "Name": {
                "title": [{"type": "text", "text": {"content": task_description}}]
            },
            # default status property (depends on DB schema)
            "Status": {"select": {"name": "Not Started"}}
        }

        if assignee:
            # Assignee property shape depends on DB: using rich_text for safe fallback
            properties["Assignee"] = {"rich_text": [{"type": "text", "text": {"content": assignee}}]}

        if due_date:
            properties["Due Date"] = {"date": {"start": due_date}}

        task = self.client.pages.create(parent={"database_id": database_id}, properties=properties)
        return task.get("id") or ""

    def update_task_status(self, task_id: str, status: str) -> None:
        """
        Update status select property for a task page.
        """
        self.client.pages.update(
            page_id=task_id,
            properties={
                "Status": {"select": {"name": status}}
            }
        )

    def get_tasks(self, database_id: str, filter_params: Optional[Dict] = None) -> List[Dict]:
        """
        Query tasks in a database. Returns list of results (may be empty).
        """
        kwargs = {"database_id": database_id}
        if filter_params:
            kwargs["filter"] = filter_params

        response = self.client.databases.query(**kwargs)
        return response.get("results", [])