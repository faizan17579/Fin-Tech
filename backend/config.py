import os


class Config:
    DEBUG = os.getenv("FLASK_DEBUG", "1") == "1"
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:27017/finforecast")
    REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


