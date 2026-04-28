#!/usr/bin/env python3
"""Test simple HTTP scraping of public Telegram channels"""

import requests
from bs4 import BeautifulSoup
import json

CHANNELS = [
    "uaejobsdaily",
    "job_crypto_uae",
    "cryptojobslist",
    "hr1win"
]

def test_telegram_web():
    """Try to scrape Telegram channel archives via web"""

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }

    for channel in CHANNELS:
        url = f"https://t.me/s/{channel}"
        print(f"\nTesting @{channel}...")
        print(f"  URL: {url}")

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            print(f"  Status: {resp.status_code}")

            if resp.status_code == 200:
                # Try to parse
                soup = BeautifulSoup(resp.content, 'html.parser')

                # Look for message containers
                messages = soup.find_all('div', class_='tgme_widget_message_bubble')
                print(f"  Found message elements: {len(messages)}")

                if messages:
                    msg = messages[0]
                    text = msg.get_text(strip=True)
                    print(f"  Sample: {text[:100]}...")
                else:
                    # Try alternative selectors
                    print(f"  (No tgme_widget_message_bubble found, trying alternatives...)")
                    divs = soup.find_all('div', class_='tgme_widget_message')
                    print(f"  Found tgme_widget_message: {len(divs)}")

            else:
                print(f"  ✗ Failed to fetch")

        except Exception as e:
            print(f"  ✗ Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    test_telegram_web()
