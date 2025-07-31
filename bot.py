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
    
    # Check bot permissions
    for guild in bot.guilds:
        member = guild.get_member(bot.user.id)
        if member and member.guild_permissions.manage_nicknames:
            print(f"✅ Bot has 'Manage Nicknames' permission in {guild.name}")
        else:
            print(f"❌ Bot missing 'Manage Nicknames' permission in {guild.name}")
    
    # Start presence XP task
    bot.loop.create_task(presence_xp_loop())
    print("⏰ Presence XP task started (15 minute intervals)")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    user_id = str(message.author.id)
    username = message.author.display_name
    
    # Update user activity
    user_activity[user_id] = {
        'username': username,
        'last_seen': datetime.now(),
        'user_obj': message.author
    }
    
    # Process message XP
    await process_message_xp(user_id, username, message.channel)
    
    # Handle commands
    if not message.content.startswith('!'):
        return
        
    print(f"📨 Command: '{message.content}' from {message.author}")
    
    if message.content == '!xp force':
        await force_presence_xp(message)
        return
    elif message.content.startswith('!xp'):
        await handle_xp_command(message)
        return
    elif message.content == '!leaderboard':
        await handle_leaderboard_command(message)
        return
    elif message.content == '!test nickname':
        # Test command per debug
        await test_nickname_update(message)
        return
    
    # Regular game commands
    data = {
        'user_id': user_id,
        'username': username,
        'command': message.content
    }
    
    # Send command to API
    result = await send_to_api(data, message.channel, 'command')
    
    # *** NICKNAME UPDATE AUTOMATICO ***
    if message.content.startswith('!join ') or message.content == '!start':
        print(f"🎨 Attempting nickname update for {message.author}")
        await asyncio.sleep(1)  # Wait for database
        success = await update_nickname_from_db(message.author)
        if success:
            print(f"✅ Nickname updated for {message.author}")
        else:
            print(f"❌ Failed to update nickname for {message.author}")

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

# === NICKNAME FUNCTIONS ===

async def update_nickname_from_db(member):
    """Aggiorna nickname basandosi sui dati del database"""
    try:
        # Get user data from database
        user_data = await get_user_faction_data(str(member.id))
        if not user_data:
            print(f"❌ No user data found for {member}")
            return False
        
        # Get base nickname (remove any existing faction emojis)
        current_nick = member.display_name
        base_nick = clean_nickname(current_nick)
        
        # Build new nickname
        if user_data.get('faction_emoji'):
            new_nick = f"{user_data['faction_emoji']} {base_nick}"
        else:
            new_nick = base_nick
        
        # Skip if already correct
        if current_nick == new_nick:
            print(f"✅ Nickname already correct for {member}")
            return True
        
        # Update nickname
        try:
            await member.edit(nick=new_nick[:32])
            print(f"✅ Updated {member}: '{current_nick}' -> '{new_nick}'")
            return True
            
        except discord.Forbidden:
            print(f"❌ No permission to change nickname for {member}")
            return False
        except discord.HTTPException as e:
            print(f"❌ Discord error changing nickname for {member}: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Error updating nickname for {member}: {e}")
        return False

def clean_nickname(nickname):
    """Remove faction emojis from nickname"""
    # List of common faction emojis
    emojis = ['🌸', '⚡', '🌊', '🔥', '🌿', '❄️', '🌙', '☀️', '⭐', '💎', 
              '🗡️', '🛡️', '🏹', '⚔️', '🔮', '📜', '🧙', '🐉', '🦅', '🐺',
              '🏰', '⚖️', '🎭', '🌺', '🍃', '💫', '🔱', '👑', '🌟', '💀']
    
    cleaned = nickname.strip()
    
    # Remove emoji if at start
    for emoji in emojis:
        if cleaned.startswith(emoji):
            cleaned = cleaned[len(emoji):].strip()
            break
    
    return cleaned if cleaned else nickname

async def get_user_faction_data(user_id):
    """Get user faction data from API"""
    try:
        url = PHP_API_URL.replace('discord.php', 'xp-handler.php')
        data = {
            'user_id': user_id,
            'action': 'get_user_data'
        }
        
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            return result.get('user_data')
        else:
            print(f"❌ API error getting user data: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error getting user faction data: {e}")
    
    return None

async def test_nickname_update(message):
    """Test command per debug nickname system"""
    member = message.author
    print(f"🧪 Testing nickname update for {member}")
    
    # Check permissions
    if not member.guild.me.guild_permissions.manage_nicknames:
        await message.channel.send("❌ Bot missing 'Manage Nicknames' permission")
        return
    
    # Get user data
    user_data = await get_user_faction_data(str(member.id))
    if not user_data:
        await message.channel.send("❌ No user data found in database")
        return
    
    current_nick = member.display_name
    base_nick = clean_nickname(current_nick)
    
    response = f"🔧 **Nickname Test Debug:**\n"
    response += f"Current nickname: `{current_nick}`\n"
    response += f"Base nickname: `{base_nick}`\n"
    response += f"Faction: {user_data.get('faction_display_name', 'None')}\n"
    response += f"Faction emoji: {user_data.get('faction_emoji', 'None')}\n"
    
    if user_data.get('faction_emoji'):
        new_nick = f"{user_data['faction_emoji']} {base_nick}"
        response += f"Target nickname: `{new_nick}`\n\n"
        
        # Try to update
        try:
            await member.edit(nick=new_nick[:32])
            response += "✅ Nickname updated successfully!"
            
        except discord.Forbidden:
            response += "❌ No permission to change nickname"
        except Exception as e:
            response += f"❌ Error: {str(e)}"
    else:
        response += "\n⚠️ No faction selected, no emoji to add"
    
    await message.channel.send(response)

# === PRESENCE XP TASK ===

async def presence_xp_loop():
    """Background task ogni 15 minuti"""
    await bot.wait_until_ready()
    print("⏰ Presence XP loop ready, waiting 15 minutes...")
    
    while not bot.is_closed():
        try:
            await asyncio.sleep(900)  # 15 minutes
            print("⏰ Processing presence XP...")
            
            current_time = datetime.now()
            processed_count = 0
            
            for user_id, activity in list(user_activity.items()):
                try:
                    time_since_activity = (current_time - activity['last_seen']).total_seconds()
                    
                    if time_since_activity < 1020:  # 17 minutes buffer
                        result = await process_presence_xp(user_id, activity['username'])
                        processed_count += 1
                        
                        if result and result.get('success') and result.get('level_up'):
                            channel = await find_announcement_channel()
                            if channel:
                                await channel.send(f"⏰ **{activity['username']}** {result['message']}")
                    
                    elif time_since_activity > 3600:
                        del user_activity[user_id]
                        
                except Exception as e:
                    print(f"❌ Error processing presence XP for {user_id}: {e}")
            
            print(f"⏰ Processed presence XP for {processed_count} active users")
            
        except Exception as e:
            print(f"❌ Presence XP loop error: {e}")

async def find_announcement_channel():
    """Find channel for announcements"""
    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name='general')
        if channel:
            return channel
        if guild.text_channels:
            return guild.text_channels[0]
    return None

# === XP PROCESSING ===

async def process_message_xp(user_id, username, channel):
    """Process message XP"""
    result = await send_xp_request('message_xp', user_id, username)
    
    if result and result.get('success') and result.get('level_up'):
        await channel.send(f"🎉 **{username}** {result['message']}")

async def process_presence_xp(user_id, username):
    """Process presence XP"""
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
    
    try:
        xp_url = PHP_API_URL.replace('discord.php', 'xp-handler.php')
        response = requests.post(xp_url, json=data, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ XP API Error {response.status_code}")
        
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
    try:
        if request_type in ['xp_stats', 'xp_cooldown', 'leaderboard']:
            url = PHP_API_URL.replace('discord.php', 'xp-handler.php')
        else:
            url = PHP_API_URL
        
        response = requests.post(url, json=data, timeout=15)
        
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
