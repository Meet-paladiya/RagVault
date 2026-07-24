"""All routers — auth, chats, documents, messages, quiz."""
from app.routers.auth import router as auth_router
from app.routers.chats import router as chats_router
from app.routers.documents import router as documents_router
from app.routers.messages import router as messages_router
from app.routers.quiz import router as quiz_router

__all__ = [
    "auth_router",
    "chats_router",
    "documents_router",
    "messages_router",
    "quiz_router",
]
