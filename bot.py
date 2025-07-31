import discord
import requests
import os
import asyncio
from datetime import datetime, timedelta

BOT_TOKEN = os.getenv('BOT_TOKEN')
PHP_API_URL = os.getenv('PHP_API_URL')

intents = discord.Intents.default()
intents.message_content = True
intents.presences = True
intents.members = True

bot = discord.Client(intents=intents)

# Track user activity for presence XP
user_activity = {}

@bot.event
async def on_ready():
    print(f'✅ Bot connected as {bot.user}')
    print(f'📡 API URL: {PHP_API_URL}')
    
    # Start presence XP task (15 minuti)
    bot.loop.create_task(presence_xp_loop())
    print("⏰ Presence XP task started (15 minute intervals)")
    print("🎨 Auto-nickname system enabled")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    user_id = str(message.author.id)
    username = message.author.display_name
    
    # Update user activity (for presence tracking)
    user_activity[user_id] = {
        'username': username,
        'last_seen': datetime.now(),
        'user_obj': message.author
    }
    
    # Process message XP for every message (ma XP solo ogni 10 messaggi)
    await process_message_xp(user_id, username, message.channel)
    
    # Handle commands
    if not message.content.startswith('!'):
        return
        
    print(f"📨 Command: '{message.content}' from {message.author}")
    
    if message.content == '!xp force':
        # Force presence XP (for testing)
        await force_presence_xp(message)
        return
    elif message.content.startswith('!xp'):
        await handle_xp_command(message)
        return
    elif message.content == '!leaderboard':
        await handle_leaderboard_command(message)
        return
    
    # Regular game commands
    data = {
        'user_id': user_id,
        'username': username,
        'command': message.content
    }
    
    result = await send_to_api(data, message.channel, 'command')
    
    # *** AGGIORNAMENTO AUTOMATICO NICKNAME ***
    # Se il comando cambia la fazione, aggiorna il nickname automaticamente
    if message.content.startswith('!join ') and result:
        await asyncio.sleep(0.5)  # Aspetta che il database sia aggiornato
        await update_user_nickname_auto(message.author)
        
    elif message.content == '!start':
        await asyncio.sleep(0.5)
        await update_user_nickname_auto(message.author)

@bot.event
async def on_member_update(before, after):
    """Track when users come online"""
    if after.status != discord.Status.offline and before.status == discord.Status.offline:
        user_id = str(after.id)
        user_activity[user_id] = {
            'username': after.display_name,
            'last_seen': datetime.now(),
            'user_obj': after
        }
        print(f"👋 {after.display_name} came online")

@bot.event
async def on_presence_update(before, after):
    """Track presence changes"""
    if after.status != discord.Status.offline:
        user_id = str(after.id)
        user_activity[user_id] = {
            'username': after.display_name,
            'last_seen': datetime.now(),
            'user_obj': after
        }

# === AUTO NICKNAME MANAGEMENT ===

async def update_user_nickname_auto(member):
    """Aggiorna automaticamente il nickname dell'utente con la sua fazione"""
    try:
        user_id = str(member.id)
        
        # Ottieni dati utente dal database
        user_data = await get_user_data(user_id)
        if not user_data:
            return
        
        # Ottieni il nickname base (senza emoji fazione)
        current_nickname = member.display_name
        base_nickname = remove_faction_emojis(current_nickname)
        
        # Se ha una fazione, aggiungi emoji
        if user_data.get('faction_emoji'):
            new_nickname = f"{user_data['faction_emoji']} {base_nickname}"
        else:
            new_nickname = base_nickname
        
        # Evita modifiche inutili
        if current_nickname == new_nickname:
            return
        
        # Prova a modificare il nickname
        try:
            await member.edit(nick=new_nickname[:32])  # Discord limit is 32 chars
            faction_name = user_data.get('faction_display_name', 'No faction')
            print(f"✅ Auto-updated nickname: {member} -> {new_nickname} ({faction_name})")
            
        except discord.Forbidden:
            print(f"⚠️ No permission to change nickname for {member}")
        except discord.HTTPException as e:
            print(f"❌ Failed to update nickname for {member}: {str(e)}")
                
    except Exception as e:
        print(f"❌ Error auto-updating nickname for {member}: {e}")

def remove_faction_emojis(nickname):
    """Rimuove emoji fazioni comuni dal nickname"""
    faction_emojis = [
        '🌸', '⚡', '🌊', '🔥', '🌿', '❄️', '🌙', '☀️', '⭐', '💎',
        '🗡️', '🛡️', '🏹', '⚔️', '🔮', '📜', '🧙', '🐉', '🦅', '🐺',
        '🏰', '⚖️', '🎭', '🌺', '🍃', '💫', '🔱', '👑', '🌟', '💀'
    ]
    
    # Rimuovi emoji all'inizio del nickname
    cleaned = nickname.strip()
    for emoji in faction_emojis:
        if cleaned.startswith(emoji):
            cleaned = cleaned[len(emoji):].strip()
            break
    
    return cleaned

async def get_user_data(user_id):
    """Ottieni dati utente dal database"""
    try:
        data = {
            'user_id': user_id,
            'action': 'get_user_data'
        }
        
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (compatible; TesseadeBot/1.0)',
        }
        
        url = PHP_API_URL.replace('discord.php', 'xp-handler.php')
        response = requests.post(url, json=data, headers=headers, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            return result.get('user_data')
        
    except Exception as e:
        print(f"❌ Error getting user data: {e}")
        
    return None

# === PRESENCE XP TASK ===

async def presence_xp_loop():
    """Background task che gira ogni 15 minuti"""
    await bot.wait_until_ready()
    print("⏰ Presence XP loop ready, waiting 15 minutes...")
    
    while not bot.is_closed():
        try:
            await asyncio.sleep(900)  # Wait 15 minutes
            print("⏰ Processing presence XP (15 min interval)...")
            
            current_time = datetime.now()
            processed_count = 0
            
            # Process XP for active users
            for user_id, activity in list(user_activity.items()):
                try:
                    # If user was active in last 17 minutes, give presence XP
                    time_since_activity = (current_time - activity['last_seen']).total_seconds()
                    
                    if time_since_activity < 1020:  # 17 minutes buffer
                        result = await process_presence_xp(user_id, activity['username'])
                        processed_count += 1
                        
                        # If level up, announce it
                        if result and result.get('success') and result.get('level_up'):
                            # Find a channel to announce
                            channel = await find_announcement_channel()
                            if channel:
                                await channel.send(f"⏰ **{activity['username']}** {result['message']}")
                    
                    # Clean old activity (older than 1 hour)
                    elif time_since_activity > 3600:
                        del user_activity[user_id]
                        
                except Exception as e:
                    print(f"❌ Error processing presence XP for {user_id}: {e}")
            
            print(f"⏰ Processed presence XP for {processed_count} active users")
            
        except Exception as e:
            print(f"❌ Presence XP loop error: {e}")

async def find_announcement_channel():
    """Find a suitable channel for announcements"""
    for guild in bot.guilds:
        # Try to find 'general' channel
        channel = discord.utils.get(guild.text_channels, name='general')
        if channel:
            return channel
        
        # Otherwise use first available text channel
        if guild.text_channels:
            return guild.text_channels[0]
    
    return None

# === XP PROCESSING FUNCTIONS ===

async def process_message_xp(user_id, username, channel):
    """Process XP from messages (ogni 10 messaggi)"""
    result = await send_xp_request('message_xp', user_id, username)
    
    # Solo mostra messaggi per XP ottenuto o level up
    if result and result.get('success'):
        if result.get('level_up'):
            await channel.send(f"🎉 **{username}** {result['message']}")

async def process_presence_xp(user_id, username):
    """Process XP from presence (ogni 15 minuti)"""
    return await send_xp_request('presence_xp', user_id, username)

async def force_presence_xp(message):
    """Force presence XP for testing"""
    user_id = str(message.author.id)
    username = message.author.display_name
    
    result = await send_xp_request('presence_xp', user_id, username)
    
    if result:
        if result.get('success'):
            if result.get('level_up'):
                await message.channel.send(f"🎉 **Force Presence XP:** {result['message']}")
            else:
                await message.channel.send(f"⏰ **Force Presence XP:** +{result.get('xp_gained', 0)} XP")
        elif result.get('type') == 'cooldown':
            remaining_time = result.get('remaining', 0)
            minutes = remaining_time // 60
            seconds = remaining_time % 60
            await message.channel.send(f"⏱️ Presence XP cooldown: {minutes}m {seconds}s remaining")
        else:
            await message.channel.send(f"❌ {result.get('error', 'Unknown error')}")
    else:
        await message.channel.send("❌ Failed to process presence XP")

async def send_xp_request(action, user_id, username):
    """Send XP request to API"""
    data = {
        'user_id': user_id,
        'username': username,
        'action': action
    }
    
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (compatible; TesseadeBot/1.0)',
    }
    
    try:
        xp_url = PHP_API_URL.replace('discord.php', 'xp-handler.php')
        
        response = requests.post(
            xp_url,
            json=data,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ XP API Error {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ XP Request Error: {e}")
        return None

# === COMMAND HANDLERS ===

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
        if request_type in ['xp_stats', 'xp_cooldown', 'leaderboard']:
            url = PHP_API_URL.replace('discord.php', 'xp-handler.php')
        else:
            url = PHP_API_URL
        
        response = requests.post(url, json=data, headers=headers, timeout=15)
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get('response'):
                await channel.send(result['response'])
                return result
            elif result.get('error'):
                await channel.send(f"❌ {result['error']}")
        else:
            await channel.send("❌ Server error occurred")
            
    except Exception as e:
        print(f"❌ API Error: {e}")
        await channel.send("❌ Connection error")
        
    return None

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
