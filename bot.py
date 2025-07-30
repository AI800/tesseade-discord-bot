import discord
import requests
import os

BOT_TOKEN = os.getenv('BOT_TOKEN')
PHP_API_URL = os.getenv('PHP_API_URL')

print(f"📡 PHP_API_URL: {PHP_API_URL}")

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
    
    try:
        response = requests.post(PHP_API_URL, json=data, timeout=10)
        print(f"📡 Status Code: {response.status_code}")
        print(f"📡 Response Headers: {response.headers}")
        print(f"📡 Raw Response: '{response.text}'")
        
        # Try to parse JSON
        try:
            result = response.json()
            print(f"📡 Parsed JSON: {result}")
            
            if result.get('response'):
                await message.channel.send(result['response'])
            else:
                await message.channel.send("❌ No response field")
                
        except Exception as json_error:
            print(f"❌ JSON Parse Error: {json_error}")
            print(f"❌ Raw response was: '{response.text[:200]}...'")
            await message.channel.send(f"❌ JSON Error: {str(json_error)[:100]}")
            
    except Exception as e:
        print(f"❌ Request Error: {e}")
        await message.channel.send("❌ Connection error")

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
