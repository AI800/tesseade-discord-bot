import discord
import requests
import os

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

PHP_API_URL = os.getenv('PHP_API_URL', 'https://tuosito.com/api/discord.php')

@bot.event
async def on_ready():
    print(f'✅ Bot connected as {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if not message.content.startswith('!'):
        return
        
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
                
    except Exception as e:
        await message.channel.send("❌ Error. Try again later.")

bot.run(os.getenv('BOT_TOKEN'))
