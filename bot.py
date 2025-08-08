import discord
import requests
import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

BOT_TOKEN = os.getenv('BOT_TOKEN')
PHP_API_URL = os.getenv('PHP_API_URL')

intents = discord.Intents.default()
intents.message_content = True
intents.presences = True
intents.members = True

bot = discord.Client(intents=intents)

# Track user activity for presence XP
user_activity = {}

# Dictionary to track duel channels and their associated data
duel_channels: Dict[int, Dict] = {}  # channel_id: {'duel_id': int, 'players': [id1, id2], 'delete_task': task}

@bot.event
async def on_ready():
    print(f'✅ Bot connected as {bot.user}')
    print(f'📡 API URL: {PHP_API_URL}')
    
    # Start presence XP task (15 minuti)
    bot.loop.create_task(presence_xp_loop())
    print("⏰ Presence XP task started (15 minute intervals)")
    
    # Start duel cleanup task
    bot.loop.create_task(cleanup_duel_channels())
    print("🗑️ Duel cleanup task started")

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
    
    # === SPECIAL COMMANDS ===
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
    elif message.content == '!debug nickname':
        await debug_nickname(message)
        return
    
    # === DUEL COMMANDS ===
    if message.content.startswith('!duel'):
        await handle_duel_command(message)
        return
    
    # === REGULAR GAME COMMANDS ===
    data = {
        'user_id': user_id,
        'username': username,
        'command': message.content
    }
    
    await send_to_api(data, message.channel, 'command')
    
    # *** NICKNAME UPDATE TRIGGERS ***
    # Update nickname when character elements change
    nickname_triggers = [
        '!join ',           # faction change
        '!choose race ',    # race change  
        '!choose spec',     # specialization change
        '!nickname ',       # custom nickname change
        '!nick '           # nickname alias
    ]
    
    if any(message.content.startswith(trigger) for trigger in nickname_triggers):
        print(f"🎨 Nickname update triggered by: {message.content}")
        await asyncio.sleep(1)  # Wait for database update
        await update_full_nickname(message.author, message.channel)

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

# === DUEL SYSTEM FUNCTIONS ===

async def handle_duel_command(message):
    """Handle !duel commands with channel context"""
    
    # Check if in a duel channel and get duel_id
    duel_id = None
    if message.channel.id in duel_channels:
        duel_id = duel_channels[message.channel.id]['duel_id']
    
    # Prepare data for PHP
    data = {
        'command': message.content,
        'user_id': str(message.author.id),
        'username': message.author.display_name,
        'duel_id': duel_id  # Include duel context
    }
    
    try:
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (compatible; TesseadeBot/1.0)',
        }
        
        response = requests.post(PHP_API_URL, json=data, headers=headers, timeout=15)
        
        if response.status_code == 200:
            result = response.json()
            
            # Handle response
            if isinstance(result, dict):
                if 'response' in result:
                    # Check for channel creation
                    if result.get('create_duel_channel'):
                        channel = await create_duel_channel(message, result['channel_data'])
                        if not channel:
                            return
                    
                    # Check for channel deletion scheduling
                    if result.get('schedule_channel_delete'):
                        await schedule_channel_deletion(
                            message.channel.id, 
                            result.get('delete_delay', 600)
                        )
                    
                    # Send the message
                    await message.channel.send(result['response'])
                    
                elif 'message' in result:
                    await message.channel.send(result['message'])
                    
                elif 'error' in result:
                    await message.channel.send(f"❌ {result['error']}")
            else:
                await message.channel.send("❌ Invalid response from server")
                
    except Exception as e:
        print(f"❌ Error in duel command: {e}")
        await message.channel.send(f"❌ Error: {e}")

async def create_duel_channel(ctx, channel_data: dict):
    """Create a private duel channel for two players"""
    guild = ctx.guild
    
    # Get the players
    try:
        player1 = guild.get_member(int(channel_data['players'][0]))
        player2 = guild.get_member(int(channel_data['players'][1]))
    except (ValueError, KeyError) as e:
        print(f"❌ Error getting players: {e}")
        await ctx.channel.send("❌ Could not find players for duel!")
        return None
    
    if not player1 or not player2:
        await ctx.channel.send("❌ Could not find one or both players!")
        return None
    
    # Create overwrites for the channel (only the two players can see and write)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        player1: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        player2: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
    }
    
    # Find or create Duels category
    category = discord.utils.get(guild.categories, name="Duels")
    if not category:
        try:
            category = await guild.create_category("Duels")
        except:
            category = None
    
    try:
        channel = await guild.create_text_channel(
            name=channel_data['name'],
            overwrites=overwrites,
            category=category,
            topic=f"Duel between {player1.display_name} and {player2.display_name}"
        )
        
        # Store channel info
        duel_channels[channel.id] = {
            'duel_id': channel_data['duel_id'],
            'players': channel_data['players'],
            'delete_task': None
        }
        
        # Send initial message
        embed = discord.Embed(
            title="⚔️ DUEL BEGINS!",
            description=f"**{player1.mention}** vs **{player2.mention}**",
            color=discord.Color.red()
        )
        embed.add_field(
            name="Commands",
            value=(
                "`!duel attack <type>` - Attack your opponent\n"
                "`!duel use <item>` - Use an item\n"
                "`!duel status` - Show current status"
            ),
            inline=False
        )
        embed.add_field(
            name="Attack Types",
            value="physical, mental, sensory, social",
            inline=False
        )
        embed.add_field(
            name="Rules",
            value=(
                "• Take turns attacking\n"
                "• First to 0 HP loses\n"
                "• Draw after 10 turns each\n"
                "• Loser is knocked out for 1 hour"
            ),
            inline=False
        )
        
        await channel.send(embed=embed)
        
        # Notify in original channel
        await ctx.channel.send(f"⚔️ Duel channel created: {channel.mention}\nPlease move there to begin!")
        
        return channel
        
    except Exception as e:
        print(f"❌ Error creating duel channel: {e}")
        await ctx.channel.send(f"❌ Failed to create duel channel: {e}")
        return None

async def schedule_channel_deletion(channel_id: int, delay: int = 600):
    """Schedule a duel channel for deletion after delay seconds"""
    if channel_id not in duel_channels:
        return
    
    async def delete_channel():
        await asyncio.sleep(delay)
        
        # Get the channel
        channel = bot.get_channel(channel_id)
        if channel:
            try:
                await channel.send("📢 This duel channel will be deleted in 10 seconds...")
                await asyncio.sleep(10)
                await channel.delete(reason="Duel ended")
                
                # Remove from tracking
                if channel_id in duel_channels:
                    del duel_channels[channel_id]
                    
            except Exception as e:
                print(f"❌ Error deleting channel: {e}")
    
    # Cancel any existing delete task
    if duel_channels[channel_id].get('delete_task'):
        duel_channels[channel_id]['delete_task'].cancel()
    
    # Create new delete task
    task = asyncio.create_task(delete_channel())
    duel_channels[channel_id]['delete_task'] = task

async def cleanup_duel_channels():
    """Background task to clean up expired duel channels"""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            # Query database for channels to delete
            data = {
                'command': '!system cleanup_duels',
                'user_id': 'system',
                'username': 'system'
            }
            
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (compatible; TesseadeBot/1.0)',
            }
            
            response = requests.post(PHP_API_URL, json=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('channels_to_delete'):
                    for channel_name in result['channels_to_delete']:
                        # Find and delete channel
                        for guild in bot.guilds:
                            channel = discord.utils.get(
                                guild.text_channels, 
                                name=channel_name
                            )
                            if channel:
                                try:
                                    await channel.delete(reason="Duel expired")
                                    print(f"🗑️ Deleted expired duel channel: {channel_name}")
                                except:
                                    pass
                        
        except Exception as e:
            print(f"❌ Cleanup error: {e}")
        
        # Run every 5 minutes
        await asyncio.sleep(300)

# === ENHANCED NICKNAME SYSTEM ===

async def update_full_nickname(member, channel):
    """Aggiorna nickname completo: [faction][race][spec] CustomName"""
    try:
        print(f"🔍 Getting full character data for {member}")
        
        # Get complete character data
        char_data = await get_character_data(str(member.id))
        if not char_data:
            print(f"❌ No character data found for {member}")
            return
        
        # Check bot permissions
        if not member.guild.me.guild_permissions.manage_nicknames:
            print(f"❌ Bot has no 'Manage Nicknames' permission in {member.guild}")
            return
        
        # Build new nickname
        new_nick = build_character_nickname(char_data)
        current_nick = member.display_name
        
        if current_nick == new_nick:
            print(f"✅ Nickname already correct for {member}: {new_nick}")
            return
        
        try:
            await member.edit(nick=new_nick[:32])  # Discord limit
            print(f"✅ Updated full nickname: {member} -> {new_nick}")
            
        except discord.Forbidden:
            print(f"❌ Permission denied changing nickname for {member}")
            if member.id != member.guild.owner_id:  # Don't spam owner
                await channel.send("⚠️ Can't change your nickname. Make sure bot role is above your role in server settings.")
            
        except discord.HTTPException as e:
            print(f"❌ Discord error for {member}: {e}")
            
    except Exception as e:
        print(f"❌ Error updating nickname for {member}: {e}")

def build_character_nickname(char_data):
    """Build nickname from character data: [emojis] CustomName"""
    emojis = []
    
    # Add faction emoji
    if char_data.get('faction_emoji'):
        emojis.append(char_data['faction_emoji'])
    
    # Add race emoji  
    if char_data.get('race_emoji'):
        emojis.append(char_data['race_emoji'])
    
    # Add specialization emoji
    if char_data.get('spec_emoji'):
        emojis.append(char_data['spec_emoji'])
    
    # Get display name (custom nickname or username)
    display_name = char_data.get('custom_nickname') or char_data.get('username') or 'Unknown'
    
    # Clean display name of any existing emojis
    clean_name = clean_all_emojis(display_name)
    
    # Build final nickname
    if emojis:
        return f"{''.join(emojis)} {clean_name}"
    else:
        return clean_name

def clean_all_emojis(text):
    """Remove all emojis from text"""
    # Extended emoji list covering factions, races, specializations
    all_emojis = [
        # Factions
        '🌸', '⚡', '🌊', '🔥', '🌿', '❄️', '🌙', '☀️', '⭐', '💎',
        '🗡️', '🛡️', '🏹', '⚔️', '🔮', '📜', '🧙', '🐉', '🦅', '🐺',
        '🏰', '⚖️', '🎭', '🌺', '🍃', '💫', '🔱', '👑', '🌟', '💀',
        '👹', '🎃', '🌋', '🌪️', '⛈️', '🌈', '🦋', '🕷️', '🐍',
        # Races  
        '👤', '🧝', '🧔', '👺', '😈', '🧚', '🦸', '🧛', '🧞', '👽',
        '🤖', '💀', '🐺', '🦅', '🐲', '🐯', '🦁', '🐻', '🦊', '🐱',
        # Specializations
        '⚔️', '🔮', '🏹', '🤝', '🗡️', '🛡️', '🔨', '🪓', '🏺', '📿',
        '💊', '🎯', '🎪', '🎨', '🎭', '🎵', '📚', '🔬', '⚗️', '🔧'
    ]
    
    cleaned = text.strip()
    
    # Remove emojis from start
    while cleaned and any(cleaned.startswith(emoji) for emoji in all_emojis):
        for emoji in all_emojis:
            if cleaned.startswith(emoji):
                cleaned = cleaned[len(emoji):].strip()
                break
    
    return cleaned if cleaned else text

async def get_character_data(user_id):
    """Get complete character data from API"""
    try:
        # Use the existing get_user_data endpoint
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
        else:
            print(f"❌ API error getting character data: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error getting character data: {e}")
        
    return None

async def debug_nickname(message):
    """Debug command per testare sistema nickname completo"""
    member = message.author
    user_id = str(member.id)
    
    response = f"🔧 **Full Nickname Debug for {member.mention}**\n\n"
    
    # Check permissions
    has_perms = member.guild.me.guild_permissions.manage_nicknames
    response += f"Bot permissions: {'✅' if has_perms else '❌'} Manage Nicknames\n"
    
    # Get current nickname
    current_nick = member.display_name
    clean_nick = clean_all_emojis(current_nick)
    response += f"Current nickname: `{current_nick}`\n"
    response += f"Clean nickname: `{clean_nick}`\n\n"
    
    # Try to get character data
    char_data = await get_character_data(user_id)
    if char_data:
        response += "**Character Data:**\n"
        
        # Faction
        if char_data.get('faction_display_name'):
            response += f"Faction: {char_data.get('faction_emoji', '❌')} {char_data['faction_display_name']}\n"
        else:
            response += "Faction: ❌ Not chosen\n"
            
        # Race
        if char_data.get('race_display_name'):
            response += f"Race: {char_data.get('race_emoji', '❌')} {char_data['race_display_name']}\n"
        else:
            response += "Race: ❌ Not chosen\n"
            
        # Specialization
        if char_data.get('spec_display_name'):
            response += f"Specialization: {char_data.get('spec_emoji', '❌')} {char_data['spec_display_name']}\n"
        else:
            response += "Specialization: ❌ Not chosen\n"
            
        # Custom nickname
        custom_nick = char_data.get('custom_nickname')
        response += f"Custom nickname: {custom_nick if custom_nick else '❌ Not set'}\n\n"
        
        # Build target nickname
        target_nick = build_character_nickname(char_data)
        response += f"**Target nickname:** `{target_nick}`\n"
        
        if target_nick != current_nick:
            response += "⚠️ Nickname needs update"
        else:
            response += "✅ Nickname is correct"
    else:
        response += "❌ Could not get character data from API"
    
    await message.channel.send(response)

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
