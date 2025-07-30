import discord
import requests
import os

BOT_TOKEN = os.getenv('BOT_TOKEN')
PHP_API_URL = os.getenv('PHP_API_URL')

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print(f'✅ Bot connected as {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if not message.content.startswith('!'):
        return
        
    print(f"📨 Command: '{message.content}' from {message.author}")
    
    data = {
        'user_id': str(message.author.id),
        'username': message.author.display_name,
        'command': message.content
    }
    
    # Headers che simulano un browser normale
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://tesseade.com/',
        'Origin': 'https://tesseade.com'
    }
    
    try:
        response = requests.post(
            PHP_API_URL, 
            json=data, 
            headers=headers,
            timeout=15
        )
        
        print(f"📡 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get('response'):
                await message.channel.send(result['response'])
                print("✅ Message sent successfully")
            else:
                await message.channel.send("❌ No response from server")
        else:
            print(f"❌ Status: {response.status_code}")
            print(f"❌ Response: {response.text}")
            await message.channel.send("❌ Server error. Please try again later.")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        await message.channel.send("❌ Connection error")

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
