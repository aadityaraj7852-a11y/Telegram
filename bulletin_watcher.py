import requests
import time
import re
import os

BULLETIN_URL = "https://dipr.rajasthan.gov.in/pages/sm/government-order/attachments/14928/85/10/2583"
LAST_PDF_FILE = "last_bulletin.txt"

def get_latest_bulletin():
    try:
        r = requests.get(BULLETIN_URL, timeout=20)
        links = re.findall(r'href="([^"]+\.pdf)"', r.text, re.IGNORECASE)

        if not links:
            return None

        latest = links[0]

        if latest.startswith("/"):
            latest = "https://dipr.rajasthan.gov.in" + latest

        return latest
    except Exception as e:
        print("Bulletin fetch error:", e)
        return None


def load_last_pdf():
    if os.path.exists(LAST_PDF_FILE):
        with open(LAST_PDF_FILE, "r") as f:
            return f.read().strip()
    return ""


def save_last_pdf(link):
    with open(LAST_PDF_FILE, "w") as f:
        f.write(link)


def start_watcher(bot, channel_id):
    while True:
        try:
            latest = get_latest_bulletin()
            last_saved = load_last_pdf()

            if latest and latest != last_saved:
                print("New Bulletin Found:", latest)

                file_data = requests.get(latest).content
                bot.send_document(channel_id, file_data, caption="📰 New e-Bulletin")

                save_last_pdf(latest)

        except Exception as e:
            print("Watcher error:", e)

        time.sleep(600)
