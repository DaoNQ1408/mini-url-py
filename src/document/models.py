from sqlalchemy import Column, Integer, String
from database import Base

class UserEntity(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String)