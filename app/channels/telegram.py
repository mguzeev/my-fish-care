"""Telegram channel implementation."""
import logging
from typing import Any, Dict, Optional
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.channels.base import BaseChannel
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.channels.texts import (
    help_text,
    start_text_existing,
    start_text_new,
    profile_text,
    profile_not_linked_text,
    echo_text,
    error_text,
)
from app.models.session import Session
import uuid
from datetime import datetime, timedelta


logger = logging.getLogger(__name__)


class TelegramChannel(BaseChannel):
    """Telegram bot channel."""
    
    def __init__(self):
        """Initialize Telegram channel."""
        super().__init__("telegram")
        self.bot_token = settings.telegram_bot_token
        self.application: Optional[Application] = None
        self.bot: Optional[Bot] = None
    
    async def start(self) -> None:
        """Start the Telegram bot."""
        if not self.bot_token:
            logger.error("Telegram bot token not configured")
            return
        
        logger.info("Starting Telegram bot...")
        
        # Create application
        self.application = Application.builder().token(self.bot_token).build()
        self.bot = self.application.bot
        
        # Register handlers
        self.application.add_handler(CommandHandler("start", self.handle_start))
        self.application.add_handler(CommandHandler("help", self.handle_help))
        self.application.add_handler(CommandHandler("profile", self.handle_profile))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Initialize application
        await self.application.initialize()
        await self.application.start()
        
        # Start polling or webhook
        if settings.telegram_use_webhook:
            # Webhook mode
            if not settings.telegram_webhook_url:
                logger.error("Webhook URL not configured")
                return
            
            webhook_url = f"{settings.telegram_webhook_url}{settings.telegram_webhook_path}"
            logger.info(f"Setting webhook to: {webhook_url}")
            
            await self.bot.set_webhook(
                url=webhook_url,
                secret_token=settings.telegram_webhook_secret,
                allowed_updates=["message", "callback_query"],
            )
            logger.info("Telegram bot started in webhook mode")
        else:
            # Polling mode
            await self.application.updater.start_polling()
            logger.info("Telegram bot started in polling mode")
        
        self.is_running = True
    
    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if self.application:
            logger.info("Stopping Telegram bot...")
            
            # Stop polling if in polling mode
            if not settings.telegram_use_webhook and self.application.updater:
                await self.application.updater.stop()
            
            # Delete webhook if in webhook mode
            if settings.telegram_use_webhook and self.bot:
                await self.bot.delete_webhook()
            
            await self.application.stop()
            await self.application.shutdown()
            self.is_running = False
            logger.info("Telegram bot stopped")
    
    async def send_message(
        self,
        recipient_id: str,
        message: str,
        **kwargs: Any
    ) -> bool:
        """
        Send a message via Telegram.
        
        Args:
            recipient_id: Telegram chat ID
            message: Message text
            **kwargs: Additional parameters (parse_mode, reply_markup, etc.)
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            if not self.bot:
                logger.error("Bot not initialized")
                return False
            
            await self.bot.send_message(
                chat_id=recipient_id,
                text=message,
                **kwargs
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False
    
    async def handle_message(self, message_data: Dict[str, Any]) -> None:
        """
        Handle incoming message (used in webhook mode).
        
        Args:
            message_data: Message data from webhook
        """
        if not self.application:
            logger.error("Application not initialized")
            return
        
        try:
            # Convert dict to Update object
            update = Update.de_json(message_data, self.bot)
            if update:
                # Process update
                await self.application.process_update(update)
        except Exception as e:
            logger.error(f"Error handling webhook message: {e}")
    
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /start command.
        
        Args:
            update: Telegram update
            context: Bot context
        """
        if not update.effective_user or not update.effective_chat:
            return
        
        user_id = update.effective_user.id
        username = update.effective_user.username
        chat_id = update.effective_chat.id
        
        async with AsyncSessionLocal() as db:
            # Check if user exists
            result = await db.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if user:
                welcome_message = start_text_existing(user.full_name or username, user.locale)
            else:
                welcome_message = start_text_new(user_id, None)
        
        await update.message.reply_text(
            welcome_message,
            parse_mode="Markdown"
        )
    
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /help command.
        
        Args:
            update: Telegram update
            context: Bot context
        """
        
        await update.message.reply_text(
            help_text(None),
            parse_mode="Markdown"
        )
    
    async def handle_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /profile command.
        
        Args:
            update: Telegram update
            context: Bot context
        """
        if not update.effective_user:
            return
        
        user_id = update.effective_user.id
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if user:
                text = profile_text(
                    name=user.full_name,
                    username=user.username,
                    email=user.email,
                    role=user.role,
                    is_active=user.is_active,
                    is_verified=user.is_verified,
                    locale=user.locale,
                )
            else:
                text = profile_not_linked_text(user_id, None)
        
        await update.message.reply_text(
            text,
            parse_mode="Markdown"
        )
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle text messages.
        
        Args:
            update: Telegram update
            context: Bot context
        """
        if not update.effective_user or not update.message:
            return
        
        user_id = update.effective_user.id
        message_text = update.message.text
        
        async with AsyncSessionLocal() as db:
            # Check if user exists and is active
            result = await db.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                await update.message.reply_text(error_text("please_start", None))
                return
            
            if not user.is_active:
                await update.message.reply_text(error_text("inactive", user.locale))
                return
            
            # Create or update session
            session_id = f"tg_{user_id}_{uuid.uuid4().hex[:8]}"
            session = Session(
                user_id=user.id,
                session_id=session_id,
                channel="telegram",
                context=None,
                expires_at=datetime.utcnow() + timedelta(hours=24),
            )
            db.add(session)
            await db.commit()
        
        # TODO: Process message with AI agent
        # For now, just echo back
        await update.message.reply_text(echo_text(message_text, user.locale))
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle callback queries from inline keyboards.
        
        Args:
            update: Telegram update
            context: Bot context
        """
        query = update.callback_query
        if not query:
            return
        
        await query.answer()
        
        # TODO: Implement callback handling
        await query.edit_message_text(
            text=f"Callback received: {query.data}"
        )


# Global Telegram channel instance
telegram_channel = TelegramChannel()

