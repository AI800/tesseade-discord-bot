import discord
import requests
import os
import asyncio
from datetime import datetime, timedelta

BOT_TOKEN = os.getenv('BOT_TOKEN')
PHP_API_URL = os.getenv('PHP_API_URL')

intents = discord.Intents.default()
intents.message_content = True
intents.presences = True  # Per tracking presenza
intents.members = True   # Per vedere membri online

bot = discord.Client(intents=intents)

# Track user presence for XP
user_presence_tracker = {}

@bot.event
async def on_ready():
    print(f'✅ Bot connected as {bot.user}')
    print(f'📡 API URL: {PHP_API_URL}')
    
    # Start presence XP task
    bot.loop.create_task(presence_xp_task())

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    # Track user activity for presence XP
    user_presence_tracker[str(message.author.id)] = datetime.now()
    
    # Process message XP (every message, with cooldown handled by PHP)
    await process_message_xp(message.author.id, message.author.display_name, message.channel)
    
    # Handle commands
    if not message.content.startswith('!'):
        return
        
    print(f"📨 Command: '{message.content}' from {message.author}")
    
    # XP-related commands
    if message.content.startswith('!xp'):
        await handle_xp_command(message)
        return
    elif message.content == '!leaderboard':
        await handle_leaderboard_command(message)
        return
    
    # Regular game commands
    data = {
        'user_id': str(message.author.id),
        'username': message.author.display_name,
        'command': message.content
    }
    
    await send_to_api(data, message.channel, 'command')

@bot.event
async def on_member_update(before, after):
    # Track when users come online/offline
    if before.status != after.status:
        if after.status != discord.Status.offline:
            user_presence_tracker[str(after.id)] = datetime.now()

# === XP SYSTEM FUNCTIONS ===

async def process_message_xp(user_id, username, channel):
    """Process XP gain from messages"""
    data = {
        'user_id': str(user_id),
        'username': username,
        'action': 'message_xp'
    }
    
    try:
        response = requests.post(
            PHP_API_URL.replace('discord.php', 'xp-handler.php'),
            json=data,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get('success') and result.get('level_up'):
                # Send level up notification
                await channel.send(f"🎉 **{username}** {result['message']}")
            # Don't send regular XP messages to avoid spam
            
    except Exception as e:
        print(f"❌ XP Error: {e}")

async def presence_xp_task():
    """Background task for presence XP"""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        await asyncio.sleep(600)  # Wait 10 minutes
        
        now = datetime.now()
        
        # Process XP for active users
        for user_id, last_activity in list(user_presence_tracker.items()):
            # If user was active in last 12 minutes, give presence XP
            if (now - last_activity).total_seconds() < 720:  # 12 minutes buffer
                
                # Get username from Discord
                try:
                    user = bot.get_user(int(user_id))
                    username = user.display_name if user else "Unknown"
                    
                    data = {
                        'user_id': user_id,
                        'username': username,
                        'action': 'presence_xp'
                    }
                    
                    response = requests.post(
                        PHP_API_URL.replace('discord.php', 'xp-handler.php'),
                        json=data,
                        headers={'Content-Type': 'application/json'},
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        
                        if result.get('success') and result.get('level_up'):
                            # Find a general channel to announce level up
                            for guild in bot.guilds:
                                channel = discord.utils.get(guild.channels, name='general')
                                if not channel:
                                    channel = guild.text_channels[0]  # First available channel
                                
                                if channel:
                                    await channel.send(f"⏰ **{username}** {result['message']}")
                                    break
                    
                except Exception as e:
                    print(f"❌ Presence XP Error for {user_id}: {e}")

async def handle_xp_command(message):
    """Handle !xp commands"""
    parts = message.content.split()
    
    if len(parts) == 1 or parts[1] == 'stats':
        # Show user's XP stats
        data = {
            'user_id': str(message.author.id),
            'username': message.author.display_name,
            'action': 'get_stats'
        }
        
        response = await send_to_api(data, message.channel, 'xp_stats')
        
    elif parts[1] == 'cooldown':
        # Show cooldown status
        data = {
            'user_id': str(message.author.id),
            'username': message.author.display_name,
            'action': 'get_cooldowns'
        }
        
        response = await send_to_api(data, message.channel, 'xp_cooldown')

async def handle_leaderboard_command(message):
    """Handle !leaderboard command"""
    data = {
        'user_id': str(message.author.id),
        'username': message.author.display_name,
        'action': 'leaderboard'
    }
    
    await send_to_api(data, message.channel, 'leaderboard')

# === UTILITY FUNCTIONS ===

async def send_to_api(data, channel, request_type):
    """Send request to PHP API"""
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (compatible; TesseadeBot/1.0)',
    }
    
    try:
        # Choose endpoint based on request type
        if request_type in ['xp_stats', 'xp_cooldown', 'leaderboard']:
            url = PHP_API_URL.replace('discord.php', 'xp-handler.php')
        else:
            url = PHP_API_URL
        
        response = requests.post(url, json=data, headers=headers, timeout=15)
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get('response'):
                await channel.send(result['response'])
            elif result.get('error'):
                await channel.send(f"❌ {result['error']}")
        else:
            await channel.send("❌ Server error occurred")
            
    except Exception as e:
        print(f"❌ API Error: {e}")
        await channel.send("❌ Connection error")

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
