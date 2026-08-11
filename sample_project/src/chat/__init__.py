"""Chat module — messaging, WebSocket sessions."""

from typing import List, Optional


class Message:
    """Chat message model."""
    def __init__(self, sender: str, receiver: str, content: str):
        self.sender = sender
        self.receiver = receiver
        self.content = content


class ChatService:
    """Core chat/messaging logic."""

    def __init__(self):
        self._messages: List[Message] = []
        self._online_users: set[str] = set()

    def send_message(self, sender: str, receiver: str, content: str) -> Message:
        """Send a message to another user."""
        msg = Message(sender, receiver, content)
        self._messages.append(msg)
        return msg

    def get_history(self, user1: str, user2: str) -> List[Message]:
        """Get conversation history between two users."""
        return [
            m for m in self._messages
            if {m.sender, m.receiver} == {user1, user2}
        ]

    def user_online(self, username: str):
        """Mark a user as online."""
        self._online_users.add(username)

    def user_offline(self, username: str):
        """Mark a user as offline."""
        self._online_users.discard(username)


class ThemeManager:
    """Manages chat UI theming."""

    def __init__(self):
        self._theme = "light"

    def set_theme(self, theme: str):
        """Change the chat theme."""
        self._theme = theme

    def get_theme(self) -> str:
        """Get the current chat theme."""
        return self._theme
