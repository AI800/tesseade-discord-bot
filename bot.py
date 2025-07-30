import discord
import requests
import os
import asyncio
from datetime import datetime

BOT_TOKEN = os.getenv('BOT_TOKEN')
PHP_API_URL = os.getenv('PHP_API_URL')

intents = discord.Intents.default()
intents.message_content = True
intents.presences = True
intents.members = True

bot = discord.Client(intents=intents)

# Debug: track XP processing
xp_debug = True

@bot.event
async def on_ready():
    print(f'✅ Bot connected as {bot.user}')
    print(f'📡 API URL: {PHP_API_URL}')
    print(f'🔍 XP Debug: {xp_debug}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    # DEBUG: Always try to process XP for non-bot messages
    if xp_debug:
        print(f"🔍 Processing message from {message.author.display_name}: '{message.content}'")
    
    # Process XP for EVERY message (not just commands)
    await process_message_xp(message.author.id, message.author.display_name, message.channel)
    
    # Handle commands
    if not message.content.startswith('!'):
        return
        
    print(f"📨 Command: '{message.content}' from {message.author}")
    
    # XP Debug commands
    if message.content == '!xp debug':
        await debug_xp_status(message)
        return
    elif message.content.startswith('!xp'):
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

# === XP SYSTEM FUNCTIONS ===

async def process_message_xp(user_id, username, channel):
    """Process XP gain from messages"""
    if xp_debug:
        print(f"🔍 Attempting XP processing for {username} (ID: {user_id})")
    
    data = {
        'user_id': str(user_id),
        'username': username,
        'action': 'message_xp'
    }
    
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (compatible; TesseadeBot/1.0)',
    }
    
    try:
        # Use XP handler endpoint
        xp_url = PHP_API_URL.replace('discord.php', 'xp-handler.php')
        
        if xp_debug:
            print(f"🔍 Sending XP request to: {xp_url}")
        
        response = requests.post(
            xp_url,
            json=data,
            headers=headers,
            timeout=15
        )
        
        if xp_debug:
            print(f"🔍 XP Response Status: {response.status_code}")
            print(f"🔍 XP Response: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            
            if xp_debug:
                print(f"🔍 XP Result: {result}")
            
            if result.get('success'):
                if result.get('level_up'):
                    # Send level up notification
                    await channel.send(f"🎉 **{username}** {result['message']}")
                elif result.get('type') != 'cooldown' and xp_debug:
                    # Debug: show XP gain (remove this in production)
                    await channel.send(f"🔍 DEBUG: {username} gained {result.get('xp_gained', 0)} XP")
            elif result.get('type') == 'cooldown' and xp_debug:
                print(f"🔍 XP Cooldown for {username}: {result.get('remaining', 0)}s remaining")
                
        else:
            if xp_debug:
                print(f"❌ XP API Error {response.status_code}: {response.text}")
            
    except Exception as e:
        if xp_debug:
            print(f"❌ XP Processing Error: {e}")

async def debug_xp_status(message):
    """Debug command to check XP status"""
    data = {
        'user_id': str(message.author.id),
        'username': message.author.display_name,
        'action': 'get_stats'
    }
    
    await send_to_api(data, message.channel, 'xp_debug')

async def handle_xp_command(message):
    """Handle !xp commands"""
    parts = message.content.split()
    
    if len(parts) == 1 or parts[1] == 'stats':
        data = {
            'user_id': str(message.author.id),
            'username': message.author.display_name,
            'action': 'get_stats'
        }
        await send_to_api(data, message.channel, 'xp_stats')
        
    elif parts[1] == 'cooldown':
        data = {
            'user_id': str(message.author.id),
            'username': message.author.display_name,
            'action': 'get_cooldowns'
        }
        await send_to_api(data, message.channel, 'xp_cooldown')

async def handle_leaderboard_command(message):
    """Handle !leaderboard command"""
    data = {
        'user_id': str(message.author.id),
        'username': message.author.display_name,
        'action': 'leaderboard'
    }
    
    await send_to_api(data, message.channel, 'leaderboard')

async def send_to_api(data, channel, request_type):
    """Send request to PHP API"""
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (compatible; TesseadeBot/1.0)',
    }
    
    try:
        # Choose endpoint
        if request_type in ['xp_stats', 'xp_cooldown', 'leaderboard', 'xp_debug']:
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
