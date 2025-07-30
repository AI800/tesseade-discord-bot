import discord
import requests
import os

# Test token validity
BOT_TOKEN = os.getenv('BOT_TOKEN')
PHP_API_URL = os.getenv('PHP_API_URL')

print(f"🔑 BOT_TOKEN length: {len(BOT_TOKEN) if BOT_TOKEN else 0}")
print(f"🔑 BOT_TOKEN starts with: {BOT_TOKEN[:10] if BOT_TOKEN else 'None'}...")
print(f"📡 PHP_API_URL: {PHP_API_URL}")

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print(f'✅ Bot connected successfully as {bot.user}')
    print(f'🔢 Bot ID: {bot.user.id}')
    print(f'📊 Connected to {len(bot.guilds)} servers')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if not message.content.startswith('!'):
        return
        
    print(f"📨 Command: '{message.content}' from {message.author}")
    
    # Simple test response first
    if message.content == '!test':
        await message.channel.send("🤖 Bot is working!")
        return
        
    # API call for other commands
    data = {
        'user_id': str(message.author.id),
        'username': message.author.display_name,
        'command': message.content
    }
    
    try:
        response = requests.post(PHP_API_URL, json=data, timeout=10)
        result = response.json()
        
        if result.get('response'):
            await message.channel.send(result['response'])
        else:
            await message.channel.send("❌ No response from server")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        await message.channel.send("❌ Connection error")

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing!")
        exit(1)
        
    print("🚀 Attempting to login...")
    try:
        bot.run(BOT_TOKEN)
    except discord.LoginFailure:
        print("❌ LOGIN FAILURE - Invalid BOT_TOKEN!")
    except Exception as e:
        print(f"❌ Connection error: {e}")
