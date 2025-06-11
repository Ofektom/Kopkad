from sqlalchemy import Column, Integer, Enum, ForeignKey
from sqlalchemy.orm import relationship
from database.postgres import Base
from models.audit import AuditMixin


class NotificationMethod:
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    BOTH = "both"


class Settings(Base, AuditMixin):
    __tablename__ = "user_settings"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    notification_method = Column(
        Enum(
            NotificationMethod.WHATSAPP,
            NotificationMethod.EMAIL,
            NotificationMethod.BOTH,
            name="notificationmethod",
        ),
        nullable=False,
    )
    user = relationship("User", back_populates="settings", foreign_keys=[user_id])
