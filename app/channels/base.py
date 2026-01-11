"""Base channel interface."""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from datetime import datetime


class BaseChannel(ABC):
    """Base class for all communication channels."""
    
    def __init__(self, name: str):
        """
        Initialize channel.
        
        Args:
            name: Channel name
        """
        self.name = name
        self.is_running = False
    
    @abstractmethod
    async def start(self) -> None:
        """Start the channel."""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel."""
        pass
    
    @abstractmethod
    async def send_message(
        self,
        recipient_id: str,
        message: str,
        **kwargs: Any
    ) -> bool:
        """
        Send a message to a recipient.
        
        Args:
            recipient_id: Recipient identifier
            message: Message text
            **kwargs: Additional parameters
            
        Returns:
            True if sent successfully, False otherwise
        """
        pass
    
    @abstractmethod
    async def handle_message(
        self,
        message_data: Dict[str, Any]
    ) -> None:
        """
        Handle incoming message.
        
        Args:
            message_data: Message data
        """
        pass
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get channel status.
        
        Returns:
            Status information
        """
        return {
            "name": self.name,
            "is_running": self.is_running,
            "timestamp": datetime.utcnow().isoformat(),
        }

