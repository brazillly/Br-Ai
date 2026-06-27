import os
import asyncio
import discord
from discord.ext import commands
from google import genai
from google.genai import types
from collections import defaultdict
import time
from datetime import datetime
import pytz # مكتبة لضبط التوقيت الصحيح
from aiohttp import web

# --- الإعدادات وتخصيص الشخصية ---
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ضع هنا آيدي القناة المخصصة التي سيرد فيها البوت بدون منشن
ALLOWED_CHANNEL_ID = 1178172943990259856  

# إعداد عميل Gemini الجديد
client = genai.Client(api_key=GEMINI_API_KEY)

# إعداد صلاحيات ديسكورد
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.presences = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
chat_sessions = {}

# نظام منع السبام (3 رسائل في 5 ثوانٍ)
user_message_timers = defaultdict(list)
SPAM_LIMIT = 3
SPAM_WINDOW = 5
COOLDOWN_TIME = 10
cooldown_users = {}

def is_spamming(user_id):
    current_time = time.time()
    if user_id in cooldown_users:
        if current_time < cooldown_users[user_id]:
            return True
        else:
            del cooldown_users[user_id]
    user_message_timers[user_id] = [t for t in user_message_timers[user_id] if current_time - t < SPAM_WINDOW]
    if len(user_message_timers[user_id]) >= SPAM_LIMIT:
        cooldown_users[user_id] = current_time + COOLDOWN_TIME
        return True
    user_message_timers[user_id].append(current_time)
    return False

async def send_long_message(channel, text):
    if len(text) <= 2000:
        await channel.send(text)
    else:
        chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]
        for chunk in chunks:
            await channel.send(chunk)
            await asyncio.sleep(0.5)

@bot.event
async def on_ready():
    print(f'✅ {bot.user.name} يعمل الآن سحابياً وبأحدث تاريخ!')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    if not is_dm and message.channel.id != ALLOWED_CHANNEL_ID:
        return

    if is_spamming(message.author.id):
        return

    async with message.channel.typing():
        channel_id = message.channel.id
        
        # جلب تاريخ اليوم وتوقيت السعودية الحالي وتمريره للبوت في كل رسالة
        tz = pytz.timezone('Asia/Riyadh')
        current_date = datetime.now(tz).strftime('%A, %B %d, %Y')
        current_time_str = datetime.now(tz).strftime('%I:%M %p')

        SYSTEM_INSTRUCTION = f"""
        You are B9 AI, a highly intelligent, helpful, and friendly AI assistant.
        - CRITICAL: Today's current date is {current_date} and the time is {current_time_str}. Always rely on this info if asked about dates or time.
        - You must support both Arabic and English perfectly, responding in the language the user uses.
        - Maintain a polite, engaging, and professional personality.
        - Keep track of the conversation context and memory.
        - Avoid using inappropriate language under any circumstances.
        """
        
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
        )
        
        # تحديث جلسة الذاكرة لتشمل التاريخ اللحظي
        if channel_id not in chat_sessions:
            chat_sessions[channel_id] = client.chats.create(model="gemini-2.5-flash", config=config)
        else:
            # تحديث الإعدادات للتاريخ الجديد
            chat_sessions[channel_id]._config = config
            
        chat = chat_sessions[channel_id]
        try:
            response = chat.send_message(message.content)
            await send_long_message(message.channel, response.text)
        except Exception as e:
            print(f"Error: {e}")
            await message.channel.send("⚠️ حدث خطأ أثناء معالجة الطلب، يرجى المحاولة لاحقاً.")

# --- سيرفر الويب الوهمي لخدعة Render مجاناً ---
async def handle(request):
    return web.Response(text="Bot is running alive!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    await start_web_server()
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
