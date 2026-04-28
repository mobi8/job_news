#!/usr/bin/env python3
"""Test Telethon access to public Telegram channels"""

import asyncio
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

# Test channels
CHANNELS = [
    "uaejobsdaily",
    "job_crypto_uae",
    "cryptojobslist",
    "hr1win"
]

async def test_channels():
    """Test if we can access public Telegram channels"""

    # Using default API credentials (for public channel access)
    # These are Telethon test credentials
    api_id = 94575
    api_hash = '32210f8c253786e8df5dfc514d93aaf4'

    # Try with non-interactive mode - skip auth if session exists
    async with TelegramClient('session_test', api_id, api_hash) as client:
        # Don't call start() - just try to use existing session or skip auth
        pass

    # Actually, let's try a simpler approach without client context
    try:
        client = TelegramClient('session_test', api_id, api_hash)
        if not await client.is_user_authorized():
            print("✗ Not authorized - need Telegram account credentials")
            print("  (Telethon requires user authentication even for public channels)")
            return

        async with client:
        print(f"✓ Connected to Telegram")

        for channel in CHANNELS:
            try:
                entity = await client.get_entity(channel)
                print(f"\n✓ Found channel: @{channel}")
                print(f"  Type: {type(entity).__name__}")
                print(f"  ID: {entity.id}")

                # Try to fetch recent messages
                messages = await client.get_messages(entity, limit=5)
                print(f"  Recent messages: {len(messages)}")

                if messages:
                    msg = messages[0]
                    print(f"  Sample message:")
                    print(f"    - Text: {msg.text[:100] if msg.text else '(no text)'}...")
                    print(f"    - Date: {msg.date}")
                    print(f"    - Sender: {msg.sender_id}")

            except Exception as e:
                print(f"✗ Channel @{channel}: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_channels())
