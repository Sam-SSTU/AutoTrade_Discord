from dotenv import load_dotenv
import os
from typing import List

load_dotenv()

# User token configuration
DISCORD_USER_TOKEN = os.getenv("DISCORD_USER_TOKEN")
DISCORD_CHANNEL_IDS = os.getenv("DISCORD_CHANNEL_IDS", "").split(",")

# User agent to mimic normal Discord client
DISCORD_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36"

# Rate limiting settings
REQUEST_DELAY = 0.5  # seconds between requests
MAX_RETRIES = 3     # Maximum number of retries for failed requests

# Discord bot intents configuration
DISCORD_INTENTS = [
    "message_content",  # Required to read message content
    "guild_messages",   # Required to receive guild messages
    "guilds",          # Required for basic guild information
    "guild_members"    # Required for member information
] 