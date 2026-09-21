from sqlalchemy import Column, Integer, String
from database import Base

class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, index=True)
    task_description = Column(String)
    reminder_time = Column(String)
    status = Column(String, default="pending")
