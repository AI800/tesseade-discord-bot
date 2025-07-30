import discord
import requests
import os
import socket

BOT_TOKEN = os.getenv('BOT_TOKEN')
PHP_API_URL = os.getenv('PHP_API_URL')

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print(f'✅ Bot connected as {bot.user}')
    print(f'📡 API URL: {PHP_API_URL}')
    
    # Test basic connectivity
    try:
        import urllib.parse
        parsed = urllib.parse.urlparse(PHP_API_URL)
        print(f"🌐 Testing DNS resolution for {parsed.hostname}...")
        ip = socket.gethostbyname(parsed.hostname)
        print(f"✅ DNS resolved to: {ip}")
    except Exception as e:
        print(f"❌ DNS error: {e}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if not message.content.startswith('!'):
        return
        
    print(f"📨 Command: '{message.content}' from {message.author}")
    
    # Test command
    if message.content == '!ping':
        await message.channel.send("🏓 Pong! Bot is alive!")
        return
    
    data = {
        'user_id': str(message.author.id),
        'username': message.author.display_name,
        'command': message.content
    }
    
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (compatible; TesseadeBot/1.0)',
        'Accept': 'application/json',
        'Cache-Control': 'no-cache'
    }
    
    try:
        print(f"🔗 Attempting connection to: {PHP_API_URL}")
        
        response = requests.post(
            PHP_API_URL, 
            json=data, 
            headers=headers,
            timeout=30,  # Increased timeout
            verify=True  # SSL verification
        )
        
        print(f"📡 Status Code: {response.status_code}")
        print(f"📡 Response Headers: {dict(response.headers)}")
        print(f"📡 Response Size: {len(response.text)} bytes")
        
        if response.status_code == 200:
            result = response.json()
            print(f"📡 JSON Response: {result}")
            
            if result.get('response'):
                await message.channel.send(result['response'])
                print("✅ Message sent successfully")
            else:
                print("⚠️ No response field in JSON")
                await message.channel.send("❌ Empty response from server")
        else:
            print(f"❌ HTTP Error {response.status_code}")
            print(f"❌ Response text: {response.text[:500]}")
            await message.channel.send(f"❌ Server returned {response.status_code}")
                
    except requests.exceptions.Timeout:
        print("⏱️ Request timeout (30s)")
        await message.channel.send("⏱️ Server timeout. Please try again.")
        
    except requests.exceptions.ConnectionError as e:
        print(f"🔌 Connection Error: {e}")
        await message.channel.send("🔌 Cannot reach server. Please try again later.")
        
    except requests.exceptions.SSLError as e:
        print(f"🔒 SSL Error: {e}")
        await message.channel.send("🔒 SSL certificate error.")
        
    except requests.exceptions.RequestException as e:
        print(f"🌐 Request Error: {e}")
        await message.channel.send("🌐 Network error occurred.")
        
    except Exception as e:
        print(f"❌ Unexpected Error: {type(e).__name__}: {e}")
        await message.channel.send("❌ Unexpected error occurred.")

if __name__ == "__main__":
    print(f"🚀 Starting bot with URL: {PHP_API_URL}")
    bot.run(BOT_TOKEN)
