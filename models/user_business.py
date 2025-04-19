from sqlalchemy import Table, Column, Integer, ForeignKey
from database.postgres import Base

user_business = Table(
    "user_business",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("business_id", Integer, ForeignKey("businesses.id"), primary_key=True),
)
