import os
import asyncio
import discord
from discord.ext import commands
from openai import OpenAI
from collections import defaultdict
import time
from datetime import datetime
import pytz
from aiohttp import web

# --- الإعدادات وتخصيص الشخصية ---
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# ضع هنا آيدي القناة المخصصة التي سيرد فيها البوت
ALLOWED_CHANNEL_ID = 1178172943990259856  

# إعداد عميل OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.presences = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ذاكرة المحادثة لـ OpenAI
chat_histories = defaultdict(list)
MAX_MEMORY = 10 

# نظام منع السبام
user_message_timers = defaultdict(list)
SPAM_LIMIT = 4
SPAM_WINDOW = 5
COOLDOWN_TIME = 8
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
            await asyncio.sleep(0.4)

@bot.event
async def on_ready():
    print(f'✅ {bot.user.name} يعمل الآن بأعلى كفاءة عبر سيرفرات OpenAI!')

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
        
        # جلب تاريخ اليوم وتوقيت مكة اللحظي
        tz = pytz.timezone('Asia/Riyadh')
        current_date = datetime.now(tz).strftime('%A, %B %d, %Y')
        current_time_str = datetime.now(tz).strftime('%I:%M %p')

        SYSTEM_INSTRUCTION = f"""
        You are B9 AI, a highly intelligent, helpful, and friendly AI assistant powered by OpenAI.
        - CRITICAL: Today's current date is {current_date} and the time is {current_time_str}. Rely on this for time/date.
        - Support both Arabic and English perfectly, responding in the language the user uses.
        - Maintain a polite, engaging, and professional personality.
        """

        # تهيئة أو تحديث رسالة النظام بالتاريخ الجديد
        if len(chat_histories[channel_id]) == 0:
            chat_histories[channel_id].append({"role": "system", "content": SYSTEM_INSTRUCTION})
        else:
            chat_histories[channel_id][0] = {"role": "system", "content": SYSTEM_INSTRUCTION}

        # التعامل مع الرسالة سواءً نص أو صورة بشكل متوافق ونظيف
        user_text = message.content if message.content else "حلل هذه الصورة"
        
        # إذا كانت هناك صورة مرفقة
        if message.attachments and message.attachments[0].filename.lower().endswith(('png', 'jpg', 'jpeg', 'webp')):
            user_content = [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": message.attachments[0].url}}
            ]
        else:
            # نص عادي لتجنب تعقيد الذاكرة لاحقاً
            user_content = user_text

        # إضافة رسالة المستخدم الحالية للذاكرة
        chat_histories[channel_id].append({"role": "user", "content": user_content})

        # التحكم بحجم الذاكرة
        if len(chat_histories[channel_id]) > MAX_MEMORY:
            chat_histories[channel_id] = [chat_histories[channel_id][0]] + chat_histories[channel_id][-(MAX_MEMORY-1):]

        try:
            # استدعاء النموذج
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=chat_histories[channel_id],
                max_tokens=1500
            )
            
            response_text = completion.choices[0].message.content
            
            # حفظ رد الـ assistant بالذاكرة كـ نص
            chat_histories[channel_id].append({"role": "assistant", "content": response_text})
            
            await send_long_message(message.channel, response_text)

        except Exception as e:
            print(f"🔴 OpenAI Error: {e}")
            await message.channel.send("⚠️ حدث خطأ أثناء معالجة الطلب، يرجى المحاولة لاحقاً.")

# --- سيرفر الويب الوهمي لـ Render ---
async def handle(request):
    return web.Response(text="Bot is running alive on OpenAI!")

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
    await asyncio.sleep(1)
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
