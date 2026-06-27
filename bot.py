import os
import asyncio
import discord
from discord.ext import commands
from google import genai
from google.genai import types
from collections import defaultdict
import time
from datetime import datetime
import pytz
import io
from aiohttp import web

# --- الإعدادات وتخصيص الشخصية ---
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ضع هنا آيدي القناة المخصصة التي سيرد فيها البوت
ALLOWED_CHANNEL_ID = 1178172943990259856  

client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.presences = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
chat_sessions = {}

# نظام منع السبام
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
    print(f'✅ {bot.user.name} جاهز للرؤية، الرسم، والرد!')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    if not is_dm and message.channel.id != ALLOWED_CHANNEL_ID:
        return

    if is_spamming(message.author.id):
        return

    # --- الميزة الأولى: طلب رسم صورة (إذا بدأت الرسالة بكلمة ارسم أو رسم أو draw) ---
    msg_lower = message.content.lower().strip()
    if msg_lower.startswith(('ارسم', 'رسم', 'draw', 'create image')):
        async with message.channel.typing():
            # استخراج الوصف من الرسالة
            prompt = message.content
            for word in ['ارسم', 'رسم', 'draw', 'create image']:
                prompt = prompt.replace(word, '', 1)
            prompt = prompt.strip()

            if not prompt:
                await message.reply("⚠️ يرجى كتابة وصف الصورة بعد كلمة ارسم. مثال: `ارسم قطة فضاء تلبس خوذة`")
                return

            try:
                # استخدام نموذج الرسم من جوجل Imagen 3
                result = client.models.generate_images(
                    model='imagen-3.0-generate-002',
                    prompt=prompt,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        output_mime_type="image/jpeg",
                        aspect_ratio="1:1"
                    )
                )
                
                # تحويل الصورة المرسلة من الـ API إلى ملف يرسل في ديسكورد
                for generated_image in result.generated_images:
                    image_bytes = io.BytesIO(generated_image.image.image_bytes)
                    discord_file = discord.File(fp=image_bytes, filename="b9_art.jpg")
                    await message.reply(content=f"🎨 تفضل هذي صورتك لـ: **{prompt}**", file=discord_file)
                    return
            except Exception as e:
                print(f"Drawing Error: {e}")
                await message.reply("⚠️ عذراً، واجهت مشكلة أثناء رسم الصورة.")
                return

    # --- الميزة الثانية: معالجة النص العادي أو قراءة الصور المرفقة ---
    async with message.channel.typing():
        channel_id = message.channel.id
        
        tz = pytz.timezone('Asia/Riyadh')
        current_date = datetime.now(tz).strftime('%A, %B %d, %Y')
        current_time_str = datetime.now(tz).strftime('%I:%M %p')

        SYSTEM_INSTRUCTION = f"""
        You are B9 AI, a highly intelligent, helpful, and friendly AI assistant.
        - CRITICAL: Today's current date is {current_date} and the time is {current_time_str}.
        - If the user sends an image, look at it, understand it completely, and answer the user's question about it.
        - Support both Arabic and English perfectly.
        """
        
        config = types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)
        
        if channel_id not in chat_sessions:
            chat_sessions[channel_id] = client.chats.create(model="gemini-2.5-flash", config=config)
        else:
            chat_sessions[channel_id]._config = config
            
        chat = chat_sessions[channel_id]

        try:
            # التحقق إذا أرسل المستخدم صورة مرفقة بالرسالة
            if message.attachments:
                attachment = message.attachments[0]
                if attachment.filename.lower().endswith(('png', 'jpg', 'jpeg', 'webp')):
                    # تحميل الصورة من ديسكورد كـ Bytes
                    img_bytes = await attachment.read()
                    
                    # إرسال الصورة مع النص المرفق إلى الذكاء الاصطناعي
                    user_text = message.content if message.content else "حلل هذه الصورة واشرح ما فيها"
                    
                    # نستخدم مكتبة types لتمرير بايتس الصورة مباشرة
                    contents = [
                        types.Part.from_bytes(data=img_bytes, mime_type=attachment.content_type),
                        user_text
                    ]
                    
                    response = chat.send_message(contents)
                    await send_long_message(message.channel, response.text)
                    return

            # إذا كانت رسالة نصية عادية بدون صورة مرفقة
            response = chat.send_message(message.content)
            await send_long_message(message.channel, response.text)
            
        except Exception as e:
            print(f"Error: {e}")
            await message.channel.send("⚠️ حدث خطأ أثناء معالجة طلبك.")

# --- سيرفر الويب الوهمي ---
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
