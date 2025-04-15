import os
import requests
from dotenv import load_dotenv

def test_telegram():
    load_dotenv()
    
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    # 1. 验证 bot token
    print("\n1. Testing bot token...")
    response = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe")
    print(f"Bot info: {response.json()}")
    
    # 2. 获取更新信息（包含chat_id）
    print("\n2. Getting updates (recent messages)...")
    response = requests.get(f"https://api.telegram.org/bot{bot_token}/getUpdates")
    updates = response.json()
    print("Updates response:", updates)
    
    if updates.get('ok') and updates.get('result'):
        for update in updates['result']:
            if 'message' in update:
                chat_id = update['message']['chat']['id']
                chat_type = update['message']['chat']['type']
                print(f"\nFound chat_id: {chat_id} (type: {chat_type})")
    else:
        print("\nNo recent messages found. Please:")
        print("1. Open Telegram")
        print("2. Find your bot (@Discord112233_bot)")
        print("3. Send a message to the bot (e.g., /start)")
        print("4. Run this script again")

if __name__ == "__main__":
    test_telegram() 