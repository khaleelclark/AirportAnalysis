import os
from dotenv import load_dotenv

load_dotenv()

AERODATABOX_API_KEY = os.getenv("AERODATABOX_API_KEY")

AIRPORTS = ["MCO", "DEN"]
