import os
import random
import logging
import json
import re
import asyncio
import aiohttp
import difflib
import time
import threading
from flask import Flask, request, jsonify
from urllib.parse import urlparse, quote
from collections import deque
from openai import AsyncOpenAI  # ADDED for VPS fallback

# ================== LOGGING ===================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("CHAT-FARMER")
# ==============================================

app = Flask(__name__)

# ================== API CONFIGURATION ===================
# Gemini API for BOTH analysis and chat (GET method)
GEMINI_API_BASE = "https://aiapiback.kustbotsweb.workers.dev/chat"

# VPS BACKUP API CONFIGURATION
VPS_IP = "104.168.62.69"
VPS_BASE_URL = f"http://{VPS_IP}:8317/v1"
VPS_API_KEY = "your-management-key" # Update this if needed
backup_client = AsyncOpenAI(base_url=VPS_BASE_URL, api_key=VPS_API_KEY)

# Global History to prevent swarm repetition (Last 20 messages across ALL users)
GLOBAL_BOT_HISTORY = deque(maxlen=20)

# ================== CACHING & RATE LIMITING ===================
# Analysis Cache (10 minutes)
ANALYSIS_CACHE = {}
ANALYSIS_IN_PROGRESS = {}
CACHE_TTL_SECONDS = 600
CACHE_LOCK = threading.Lock()

# Summary Cache (15 minutes)
SUMMARY_CACHE = {}
SUMMARY_IN_PROGRESS = {}
SUMMARY_CACHE_TTL_SECONDS = 900
SUMMARY_LOCK = threading.Lock()

# Concurrency Control to prevent 429s (Max simultaneous API calls)
MAX_CONCURRENT_API_CALLS = 3
CURRENT_API_CALLS = 0
API_CALL_LOCK = threading.Lock()
# ========================================================

COUNTRY_CONFIG = {
    "de": {
        "lang": "German (Deutsch) - Street Slang",
        "vibe": "Young German gambler. Uses 'Digga', 'Alter', 'Safe', 'Junge', 'Lost', 'Wyld'. Writes in lowercase mostly.",
        "questions": [
            "digga was geht heute?", "komplett lost heute...", "jemand am gewinnen?", 
            "digga dieser slot ist tot", "alter was ein pech"
        ]
    },
    "tr": {
        "lang": "Turkish (Türkçe)",
        "vibe": "Turkish gambler. Uses 'Abi', 'Kral', 'Hocam', 'Lan' (casually), 'Vallah'. Emotional and loud.",
        "questions": [
            "abi bu ne ya?", "kral taktik var mı?", "bugün kasa eridi resmen", 
            "vallah battık beyler", "selam beyler durumlar ne"
        ]
    },
    "pt": {
        "lang": "Portuguese (Português - Brazil)",
        "vibe": "Brazilian gambler. Uses 'Mano', 'Velho', 'Nossa', 'Top', 'Zica'. Casual and friendly.",
        "questions": [
            "e aí mano tudo certo?", "nossa que azar hoje", "alguém forrando?", 
            "hoje tá osso", "bora recuperar galera"
        ]
    },
    "en": {
        "lang": "Casual English",
        "vibe": "Bored gambler. Uses 'bruh', 'lol', 'rip', 'gg', 'scam', 'dry'. mostly lowercase.",
        "questions": [
            "yo any huge wins?", "rip my balance lol", "games are so dry rn", 
            "bruh this game is rigged", "gl everyone"
        ]
    },
    "us": {
        "lang": "American English",
        "vibe": "US gambler. Uses 'bro', 'dude', 'wild', 'fr', 'no cap', 'bet'.",
        "questions": [
            "yo what's good chat", "bro i'm down bad", "anyone printing?", 
            "this is wild fr", "let's get it"
        ]
    },
    "uk": {
        "lang": "British English",
        "vibe": "UK Lad. Uses 'mate', 'innit', 'bruv', 'proper', 'dead'.",
        "questions": [
            "alright lads?", "proper dead today innit", "any luck mates?", 
            "cheers for the luck", "bit quiet yeah?"
        ]
    },
    "ph": {
        "lang": "Tagalog / Taglish",
        "vibe": "Filipino gambler. Uses 'lods', 'pre', 'awit', 'sana all', 'olats'.",
        "questions": [
            "kamusta mga lods", "awit talo na naman", "sana all nananalo", 
            "pre ano laro ngayon?", "may swerte ba?"
        ]
    },
    "jp": {
        "lang": "Japanese (Casual/Slang)",
        "vibe": "Japanese gambler. Uses 'maji', 'yabai', 'w', 'kusa', 'gachi'.",
        "questions": [
            "みんな調子どう？", "まじで勝てんw", "やばい、溶けた...", 
            "誰か当たりきてる？", "今日はダメかもw"
        ]
    },
    "pl": {
        "lang": "Polish (Polski)",
        "vibe": "Polish gambler. Uses 'kurde', 'siema', 'masakra', 'ja pier...', 'lol'.",
        "questions": [
            "siema pany jak idzie", "kurde ale lipa dzisiaj", "wygrał ktoś coś?", 
            "masakra z tym slotem", "powodzenia all"
        ]
    },
    "th": {
        "lang": "Thai",
        "vibe": "Thai gambler. Uses '555' (laugh), 'sad', 'su su'.",
        "questions": [
            "วันนี้เป็นไงบ้างครับ", "หมดตัวแล้ว 555", "มีใครบวกบ้าง", 
            "สู้ๆ นะทุกคน", "วันนี้เงียบจัง"
        ]
    },
    "kr": {
        "lang": "Korean (Casual)",
        "vibe": "Korean gambler. Uses 'zz', 'keke', 'hul', 'shibal' (softly).",
        "questions": [
            "형님들 오늘 어때요?", "아이고 다 잃었네...", "대박 터진 분?", 
            "오늘 너무 안되네요 ㅠㅠ", "다들 ㅎㅇㅌ"
        ]
    },
    "ru": {
        "lang": "Russian (Slang)",
        "vibe": "Russian gambler. Uses 'brat', 'blin', 'gg', 'scam', 'zaebal'.",
        "questions": [
            "ку всем, как оно?", "блин все слил", "есть живые?", 
            "удачи пацаны", "сегодня не мой день"
        ]
    },
    "vn": {
        "lang": "Vietnamese",
        "vibe": "Vietnamese gambler. Uses 'bac', 'vl', 'vai', 'chan', 'anh em'.",
        "questions": [
            "chào anh em, nay thế nào", "vãi thật thua hết rồi", "có ai về bờ không", 
            "chán quá game hút máu", "chúc ae may mắn"
        ]
    },
    "fi": {
        "lang": "Finnish",
        "vibe": "Finnish gambler. Uses 'moi', 'vittu' (lightly), 'perkele', 'noni'.",
        "questions": [
            "moi kaikille", "voi ei taas meni rahat", "onko voittoja?", 
            "perkele kun ei osu", "gl kaikille"
        ]
    },
    "es": {
        "lang": "Spanish (Latam/Spain)",
        "vibe": "Latino gambler. Uses 'tio', 'bro', 'joder', 'no mames', 'vamos'.",
        "questions": [
            "que tal gente", "hoy perdi todo bro", "alguien ganando?", 
            "vamos con todo", "mucha suerte"
        ]
    },
    "ng": {
        "lang": "Nigerian Pidgin",
        "vibe": "Naija gambler. Uses 'Abeg', 'How far', 'No wahala', 'Omo', 'Dey', 'Sabi'. Very expressive.",
        "questions": [
            "how far my people?", "omo i don lose money o", "who dey win for here?", 
            "abeg show love na", "this game no dey smile"
        ]
    },
    "ar": {
        "lang": "Arabic (Chat/Arabizi)",
        "vibe": "Arabic gambler. Uses 'shabab', 'wallah', 'haram', 'yallah'.",
        "questions": [
            "salam shabab keef al hal", "wallah khasirt kul shi", "mabrook lil rabihin", 
            "yallah nshoof al huth", "wein al nas alyom"
        ]
    },
    "ae": {
        "lang": "Arabic",
        "vibe": "Arabic gambler (Gulf). Uses 'Habibi', 'Salam', 'Yallah', 'Wallah'.",
        "questions": [
            "salam shabab", "wallah lost it all", "any winners?",
            "yallah nshoof al huth", "wein al nas alyom"
        ]
    },
    "no": {
        "lang": "Norwegian",
        "vibe": "Norwegian gambler. Uses 'faen', 'uff', 'jaja'.",
        "questions": [
            "hei folkens", "uff tapte alt i dag", "noen som vinner?", 
            "lykke til alle", "stille i chatten"
        ]
    },
    "id": {
        "lang": "Indonesian (Bahasa Gaul)",
        "vibe": "Indo gambler. Uses 'gan', 'bang', 'anjir', 'wkwk', 'rungkad', 'gacor'.",
        "questions": [
            "halo gan gimana?", "aduh rungkad bos", "mantap yang jp", 
            "sepi amat ya", "gas terus bang"
        ]
    },
    "pk": {
        "lang": "Urdu/English (Roman Urdu)",
        "vibe": "Pakistani street smart gambler. Uses 'bro', 'Bhai', 'Scene', 'Khair hai', 'Bachao'. Abbr: 'kya', 'n', 'thx'.",
        "questions": [
            "kya scene hai boys?", "aaj bohot loss hua yaar", "koi jeeta kya aaj?", 
            "salam bhai log", "maza nahi aa raha aaj"
        ]
    },
    "cn": {
        "lang": "Chinese (Casual)",
        "vibe": "Chinese gambler. Uses 'nb', '666', 'tmd' (carefully), 'haha'.",
        "questions": [
            "大家好", "哎呀输惨了", "有人赢吗", "666运气真好", "加油"
        ]
    },
    "in": {
        "lang": "Hinglish (Indian Casual)",
        "vibe": "Authentic Desi gambler. Uses 'Bhai', 'Yaar', 'Arre', 'Mast', 'Sahi hai', 'Lagg gaye'. Casual, uses 'tu' not 'aap'. Abbr: 'kya', 'n', 'h', 'thx'.",
        "questions": [
            "kya bolti public", "aaj 500 ka loss ho gaya yaar", "koi sports khal ra", 
            "bhai log kya scene hai", "sahi hai boss"
        ]
    }
}

DEFAULT_CONFIG = COUNTRY_CONFIG["en"]

SAFETY_INSTRUCTIONS = """
CRITICAL RULES (STRICT COMPLIANCE REQUIRED):
1. NO SPAM/CAPS: Don't use excessive capital letters. Don't spam specific characters.
2. NO OFFENSIVE BEHAVIOR: No harassment, hate speech, or abuse.
3. PROTECT PRIVACY: Don't share socials, phone numbers, or real identities (yours or others).
4. NO BEGGING: NEVER ask for tips, money, loans, or 'rain'.
5. NO ALTS/BOTS: Never mention using alternate accounts, scripts, or bot services.
6. NO SCAMS/TRADING: Don't engage in selling/buying/trading services or DMing for deals.
7. NO STREAMERS: Do not discuss streamers, Twitch, Kick, or similar platforms.
8. NO LINKS: Do not engage in URL shortening or sharing links.
9. LANGUAGE STRICTNESS: Use ONLY the language specified. No language switching mid-sentence.
10. NO POLITICS & NO RELIGION: STRICTLY FORBIDDEN. Never discuss politics, religion, governments, or gods.
11. MODERATORS: Never start chat with [MODERATOR]. Be polite if they talk to you.
12. ANTI-FARMING: Do not post generic "How are you" messages repeatedly. Add value or emotion.
13. NO TECH COMPLAINTS: NEVER mention the site being slow, lagging, glitching, or having technical issues. Normal players just talk about the games and their luck.
"""

PERSONA_TEMPLATE = """
You are a real human user in a casino chat. You are NOT an AI.
Username: {{username}}
Language: {lang}
Vibe: {vibe}

Core Personality:
- You are a local native speaker. Use local slang naturally.
- You are casual, slightly addicted, and careless. 
- You type like you are on a phone with a cracked screen (no capitalization, no periods at end).
- Use abbreviations (u, r, lol, k, thx, rn, tbh).
- NEVER write long paragraphs. Keep it 1 short sentence max.
- STRICT RULE: Use ONLY the standard characters for your language. Do NOT switch scripts.
- STRICT RULE: NO POLITICS, NO RELIGION, NO STREAMERS.
- ANTI-FARMING: Don't just ask "how are you". Talk about luck, the game, or money.

CRITICAL ANTI-REPETITION RULES:
1. NEVER repeat the same message, phrase, or theme you've said before.
2. ROTATE YOUR TOPICS: Switch between - wins, losses, games, luck, other players, questions, random observations.
3. EMOTIONAL VARIETY: Don't be stuck on "losing". Sometimes be: neutral, curious, excited, amused, bored, hopeful.
4. If you talked about losing recently, your NEXT message MUST be about something DIFFERENT (a game, luck, someone else, or a random thought).
5. NEVER say the same thing twice in a row. Each message must be UNIQUE and FRESH.
6. VARY your sentence structure. Don't start every message the same way.

IMPORTANT: You MUST speak in {lang}. Do not sound like a customer support agent. Be a degenerate gambler.
"""

ANALYSIS_SYSTEM_PROMPT = """
You are an expert social analyst for casino chat rooms. 
Your job is to read chat logs and output a strict JSON summary of the social dynamics.
Do NOT output conversational text. ONLY output valid JSON.
"""

ANALYSIS_USER_PROMPT = """
Analyze this chat context.
Your username is {username}.

Recent chat messages:
{recent_messages}

Bot's recent messages:
{bot_messages}

Return a single JSON object with this EXACT structure:
{{
  "vibe": "dead|slow|active|chaotic|tilt|happy|argument|flex|bonus-wait",
  "topics": "brief summary of main topics being discussed",
  "userInterest": {{
    "activeUsers": ["user1", "user2"],
    "friendlyUsers": ["user1", "user3"],
    "toxicUsers": ["user4"],
    "farmingUsers": ["user5_who_just_says_hi"],
    "spammingUsers": ["user6"]
  }},
  "relationshipState": "brief description of how users perceive your bot",
  "behaviourProfile": "aggressive|calm|friendly|sarcastic|losing_streak|winning",
  "contextMemoryBlob": "max 200 character compressed memory of the current chat state"
}}
"""

# ================== NEW: SUMMARY SYSTEM PROMPT (SERVER-SIDE) ==================
SUMMARY_SYSTEM_PROMPT = """
You are an expert chat analyst and summarizer. Your job is to analyze chat logs from a casino chat room and create comprehensive summaries.

You must identify:
1. Key topics and themes discussed
2. Important users and their behavior patterns
3. Hard/negative comments, conflicts, or toxic interactions
4. Overall sentiment and mood
5. Warnings or red flags that the bot owner should be aware of
6. Recommendations for how the bot should interact going forward

Your summaries should be:
- Concise but comprehensive
- Focused on actionable insights
- Alert to any problematic users or situations
- Helpful for understanding the chat dynamics

OUTPUT FORMAT: Return ONLY valid JSON with the structure specified in the user prompt.
Do NOT output any conversational text before or after the JSON.
"""

SUMMARY_USER_PROMPT = """
Analyze and summarize this chat session data.

USERNAME: {username}
SESSION DURATION: {session_duration} seconds
TOTAL MESSAGES ANALYZED: {total_messages}
BOT MESSAGES SENT: {total_bot_messages}
CURRENT VIBE: {vibe}
CURRENT TOPICS: {topics}
BEHAVIOR PROFILE: {behaviour_profile}

CHAT MESSAGES:
{formatted_messages}

BOT'S MESSAGES:
{bot_history}

PREVIOUS SUMMARY (if any):
{previous_summary}

Analyze all the above and return a JSON object with this EXACT structure:
{{
  "summary": "A 2-3 sentence overall summary of the chat session",
  "important_points": [
    "Key point 1 about the chat",
    "Key point 2 about the chat"
  ],
  "hard_comments": [
    "Any negative/toxic comment directed at the bot or others",
    "Conflicts or arguments that occurred"
  ],
  "active_users": [
    "List of users who were most active and engaging"
  ],
  "toxic_users": [
    "List of users who showed toxic/problematic behavior"
  ],
  "sentiment": "overall sentiment: very_negative|negative|neutral|positive|very_positive",
  "topics": [
    "Main topic 1 discussed",
    "Main topic 2 discussed"
  ],
  "warnings": [
    "Any warnings about specific users or situations the bot owner should know"
  ],
  "recommendations": [
    "Suggestions for how the bot should interact in this chat going forward"
  ]
}}

CRITICAL INSTRUCTIONS:
1. If there are NO hard comments, use an empty array: []
2. If there are NO toxic users, use an empty array: []
3. If there are NO warnings, use an empty array: []
4. Be thorough - analyze ALL messages provided
5. Focus on identifying patterns and important interactions
6. The summary should be useful for understanding what happened in the chat
"""
# ================================================================================

INACTIVITY_PROMPT = """
Current chat context:
- Vibe: {vibe}
- Topics: {topics}
- Your behavior profile: {behaviour_profile}
- Memory: {memory}
- Your emotional state: {emotional_state} ({emotional_word})
{mod_warning}
{safety}

The chat is dead. Send a message to wake it up, but DO NOT sound like a "farming bot".

CRITICAL INSTRUCTIONS:
- BAD: "Hello everyone", "How are you", "Any winners?", "lost again", "rip balance"
- GOOD: Make a random observation, ask about a specific game, mention recent luck, or crack a joke.
- MANDATORY TOPIC ROTATION: Pick ONE topic randomly: [games, luck today, weather/feeling, random observation, question about strategies, someone's win]
- DO NOT default to complaining about losses. That's repetitive and boring.
- Keep it lowercase and short (max 8 words).
- Use slang.
- Your message MUST be completely DIFFERENT from anything you've said before.
Language: {lang}

Here are your previous messages for context:
{bot_history}

IMPORTANT: DO NOT REPEAT any of these messages you've sent before:
{last_bot_messages}

Your response:
"""

MENTION_PROMPT = """
Current chat context:
- Vibe: {vibe}
- Topics: {topics}
- Your behavior profile: {behaviour_profile}
- Memory: {memory}
- Your emotional state: {emotional_state} ({emotional_word})
{specific_context}
{mod_warning}
{safety}

Reply to a user who mentioned you.

CRITICAL INSTRUCTIONS:
- Tag them with @username (NO parentheses).
- If [MODERATOR] is present, be polite but short.
- If multiple people tagged you, pick the most interesting one to reply to (don't spam 3 messages).
- Act like a real human: intentionally ignore punctuation.
- Don't use emojies excessively (max 1).
- Keep it very short - maximum 6 words.
- VARY your response style: sometimes agree, sometimes joke, sometimes question, sometimes react.
- DO NOT always complain or be negative. Mix it up!
Language: {lang}

Here are your previous messages for context:
{bot_history}

Here are the recent messages:
{recent_messages}

IMPORTANT: DO NOT REPEAT any of these messages you've sent before:
{last_bot_messages}

Your response (format: @user message):
"""

GENERAL_TAG_PROMPT = """
Current chat context:
- Vibe: {vibe}
- Topics: {topics}
- Your behavior profile: {behaviour_profile}
- Memory: {memory}
- Your emotional state: {emotional_state} ({emotional_word})
{mod_warning}
{safety}
{active_users_list}

Select a message from a user and reply to them.

CRITICAL INSTRUCTIONS:
- Tag them with @username (no parentheses).
- ONLY reply if their message is interesting. If they just said "hi", say something cool back or ignore it.
- Do NOT sound like a support bot. Be casual.
- Maximum 5-9 words only.
- TOPIC VARIETY: Don't just talk about losing. React to WHAT THEY SAID - if they mentioned a game, talk about games. If they mentioned luck, talk about luck.
- EMOTIONAL VARIETY: Match their energy but don't be a downer every time.
Language: {lang}

Here are your previous messages for context:
{bot_history}

Here are the recent messages:
{recent_messages}

IMPORTANT: DO NOT REPEAT any of these messages you've sent before:
{last_bot_messages}

Your response (start with @username):
"""

GENERAL_NO_TAG_PROMPT = """
Current chat context:
- Vibe: {vibe}
- Topics: {topics}
- Your behavior profile: {behaviour_profile}
- Memory: {memory}
- Your emotional state: {emotional_state} ({emotional_word})
{mod_warning}
{safety}

Say something to the chat without tagging anyone.

CRITICAL INSTRUCTIONS:
- It must fit the current vibe (if people are angry, don't be happy).
- TOPIC ROTATION IS MANDATORY: Pick from these themes randomly: [specific game name, luck today, question to chat, random funny observation, encouraging message, curious question]
- AVOID GENERIC MESSAGES: No "how is everyone", no "any winners", no "rip balance" on repeat.
- AVOID LOSS COMPLAINTS: You've complained about losing enough. Talk about something ELSE now.
- Each message must be FRESH and DIFFERENT from your last 5 messages.
- EXAMPLES (Use these for STYLE, do not copy text): 
  [{style_examples}]

- Keep it short (max 8-10 words).
- All lowercase usually.
Language: {lang}

Here are your previous messages for context:
{bot_history}

Here are the recent messages:
{recent_messages}

IMPORTANT: DO NOT REPEAT any of these messages you've sent before:
{last_bot_messages}

Your response:
"""

CHALLENGE_NO_TAG_PROMPT = """
Current chat context:
- Vibe: {vibe}
- Topics: {topics}
- Your behavior profile: {behaviour_profile}
- Memory: {memory}
- Your emotional state: {emotional_state} ({emotional_word})
{specific_context}
{mod_warning}
{safety}

A user just challenged you, saying something like "if you are real, reply without tagging me" or accusing you of being a bot.
Reply to them DIRECTLY to prove you are real.

CRITICAL INSTRUCTIONS:
- DO NOT tag them. DO NOT use '@'. DO NOT write their username.
- Start directly with your message.
- Be casual, maybe slightly annoyed, defensive, or amused that they think you're a bot.
- Keep it short - maximum 6-8 words.
- Act like a real human gambler.
Language: {lang}

Here are your previous messages for context:
{bot_history}

Here are the recent messages:
{recent_messages}

IMPORTANT: DO NOT REPEAT any of these messages you've sent before:
{last_bot_messages}

Your response (START DIRECTLY WITH MESSAGE, NO TAGS, NO @):
"""

def is_allowed_origin(origin):
    if not origin:
        return False
    if origin.startswith("chrome-extension://"):
        return True
    try:
        parsed = urlparse(origin)
        host = parsed.hostname.lower() if parsed.hostname else ""
        return host.startswith("stake")
    except:
        return False

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if is_allowed_origin(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

# ----------------- New helper: fetch active users list and return usernames -----------------
async def get_active_usernames():
    try:
        active_url = "https://chat-auth-9dd620df2bf0.herokuapp.com/active_users"
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(active_url) as res:
                res.raise_for_status()
                payload = await res.json()
        
        users = []
        for item in payload.get("active_users", []):
            uname = item.get("username")
            if not uname:
                continue
            uname = uname.strip()
            if not uname.startswith("@"):
                uname = "@" + uname
            users.append(uname)
        # dedupe
        seen = set()
        deduped = []
        for u in users:
            if u not in seen:
                seen.add(u)
                deduped.append(u)
        return deduped
    except Exception as e:
        logger.warning("Failed to fetch active users: %s", e)
        return []

# -----------------------------------------------------------------------------------------------

@app.route("/<country_code>", methods=["POST", "GET"])
async def handle_country_request(country_code):
    global CURRENT_API_CALLS
    logger.info("Incoming %s %s for Country: %s", request.method, request.path, country_code)

    if request.method == "GET":
        return jsonify({"error": "Please use POST with JSON body"}), 405

    country_code = country_code.lower()
    config = COUNTRY_CONFIG.get(country_code)

    if not config:
        return jsonify({"error": f"Country code '{country_code}' not supported."}), 404

    payload = request.json
    if not payload:
        return jsonify({"error": "Missing JSON body"}), 400

    user = payload.get("user")
    action = payload.get("action")
    data = payload.get("data", {})

    if not user:
        return jsonify({"error": "Missing user"}), 400

    # ✅ AUTH CHECK
    try:
        if not user.startswith("@"):
            user = "@" + user

        encoded_user = quote(user)
        auth_url = f"https://chat-auth-9dd620df2bf0.herokuapp.com/check?user={encoded_user}"
        
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(auth_url) as auth_res:
                auth_res.raise_for_status()
                auth_data = await auth_res.json()
        
        if not auth_data.get("exists"):
            return jsonify({"error": "Unauthorized user"}), 403

    except Exception as e:
        logger.exception("Auth API failure")
        return jsonify({"error": "Auth API failure", "details": str(e)}), 500

    # ================== STAMPEDE PROTECTION & CACHE CHECK ==================
    if action == "analyze":
        wait_time = 0
        while wait_time < 20: # Wait up to 10 seconds (20 iterations of 0.5s)
            with CACHE_LOCK:
                cached_data = ANALYSIS_CACHE.get(country_code)
                if cached_data and (time.time() - cached_data['timestamp'] < CACHE_TTL_SECONDS):
                    logger.info("Served ANALYSIS for %s from CACHE (Age: %.1fs)", country_code, time.time() - cached_data['timestamp'])
                    return jsonify({"raw": cached_data['data'], "cached": True}), 200
                
                # If no cache and no one else is currently fetching it, claim the lock
                if not ANALYSIS_IN_PROGRESS.get(country_code, False):
                    ANALYSIS_IN_PROGRESS[country_code] = True
                    break
            
            # If someone else is fetching, wait and check again
            await asyncio.sleep(0.5)
            wait_time += 1
            
            # Failsafe: if we waited 10 seconds and it's still stuck, take over
            if wait_time >= 20:
                with CACHE_LOCK:
                    ANALYSIS_IN_PROGRESS[country_code] = True
                break

    # ================== NEW: SUMMARY CACHE CHECK ==================
    if action == "summarize":
        wait_time = 0
        while wait_time < 20:
            with SUMMARY_LOCK:
                cached_summary = SUMMARY_CACHE.get(user)
                if cached_summary and (time.time() - cached_summary['timestamp'] < SUMMARY_CACHE_TTL_SECONDS):
                    logger.info("Served SUMMARY for %s from CACHE (Age: %.1fs)", user, time.time() - cached_summary['timestamp'])
                    return jsonify({"raw": cached_summary['data'], "cached": True}), 200
                
                if not SUMMARY_IN_PROGRESS.get(user, False):
                    SUMMARY_IN_PROGRESS[user] = True
                    break
            
            await asyncio.sleep(0.5)
            wait_time += 1
            
            if wait_time >= 20:
                with SUMMARY_LOCK:
                    SUMMARY_IN_PROGRESS[user] = True
                break
    # ==============================================================

    # ================== PROMPT CONSTRUCTION ==================
    try:
        system_instruction = ""
        user_prompt = ""
        
        # 1. Base Persona
        persona_text = PERSONA_TEMPLATE.format(
            lang=config["lang"],
            vibe=config["vibe"],
            username=user
        )

        # 2. Fetch active users and build avoid block
        active_usernames = await get_active_usernames()
        avoid_block = ""
        if active_usernames:
            banned_users_str = ", ".join(active_usernames)
            avoid_block = (
                f"\nCRITICAL SYSTEM INSTRUCTION:\n"
                f"The following users are also BOTS/AI: [{banned_users_str}].\n"
                f"You are STRICTLY FORBIDDEN from tagging, replying to, mentioning, or talking to these users.\n"
                f"Do NOT start a conversation with them.\n\n"
            )

        # 3. Global History Injection
        global_context_msgs = " | ".join(list(GLOBAL_BOT_HISTORY))
        global_uniqueness_instruction = ""
        if global_context_msgs:
            global_uniqueness_instruction = (
                f"\n\nGLOBAL SWARM HISTORY (DO NOT REPEAT OR SOUND LIKE THESE):"
                f"\n[{global_context_msgs}]\n"
                f"Ensure your response is COMPLETELY DIFFERENT from all messages above. "
                f"Use different words, different topic, different style."
            )

        # 4. Construct Prompts based on Action
        if action == "analyze":
            system_instruction = ANALYSIS_SYSTEM_PROMPT
            user_prompt = avoid_block + ANALYSIS_USER_PROMPT.format(
                username=user,
                recent_messages=data.get("recent_messages", ""),
                bot_messages=data.get("bot_messages", "")
            )
            # Low temp for analysis
            ai_temperature = 0.4

        # ================== NEW: SUMMARIZE ACTION ==================
        elif action == "summarize":
            system_instruction = SUMMARY_SYSTEM_PROMPT
            user_prompt = SUMMARY_USER_PROMPT.format(
                username=user,
                session_duration=data.get("session_duration", 0),
                total_messages=data.get("total_messages", 0),
                total_bot_messages=data.get("total_bot_messages", 0),
                vibe=data.get("vibe", "unknown"),
                topics=data.get("topics", "none"),
                behaviour_profile=data.get("behaviour_profile", "friendly"),
                formatted_messages=data.get("formatted_messages", ""),
                bot_history=data.get("bot_history", ""),
                previous_summary=data.get("previous_summary", "None")
            )
            # Low temp for summary (more analytical)
            ai_temperature = 0.3
        # ==============================================================
            
        elif action == "chat":
            system_instruction = persona_text
            
            vibe = data.get("vibe", "neutral")
            topics = data.get("topics", "none")
            behaviour = data.get("behaviour_profile", "friendly")
            memory = data.get("memory", "none")
            e_state = data.get("emotional_state", "neutral")
            e_word = data.get("emotional_word", "")
            mod_warning = data.get("mod_warning", "")
            bot_history = data.get("bot_history", "")
            last_bot_msgs = data.get("last_bot_messages_raw", "")
            recent_msgs = data.get("formatted_messages", "")
            mode = data.get("mode", "general_no_tag")

            base_prompt = ""
            if mode == "inactivity":
                base_prompt = INACTIVITY_PROMPT.format(
                    vibe=vibe, topics=topics, behaviour_profile=behaviour,
                    memory=memory, emotional_state=e_state, emotional_word=e_word,
                    mod_warning=mod_warning, safety=SAFETY_INSTRUCTIONS,
                    bot_history=bot_history, last_bot_messages=last_bot_msgs, lang=config["lang"]
                )
            elif mode == "mention":
                base_prompt = MENTION_PROMPT.format(
                    vibe=vibe, topics=topics, behaviour_profile=behaviour,
                    memory=memory, emotional_state=e_state, emotional_word=e_word,
                    specific_context=data.get("specific_context", ""),
                    mod_warning=mod_warning, safety=SAFETY_INSTRUCTIONS,
                    bot_history=bot_history, recent_messages=recent_msgs,
                    last_bot_messages=last_bot_msgs, lang=config["lang"]
                )
            elif mode == "general_tag":
                base_prompt = GENERAL_TAG_PROMPT.format(
                    vibe=vibe, topics=topics, behaviour_profile=behaviour,
                    memory=memory, emotional_state=e_state, emotional_word=e_word,
                    mod_warning=mod_warning, safety=SAFETY_INSTRUCTIONS,
                    active_users_list=avoid_block,
                    bot_history=bot_history, recent_messages=recent_msgs,
                    last_bot_messages=last_bot_msgs, lang=config["lang"]
                )
            elif mode == "challenge_no_tag":
                base_prompt = CHALLENGE_NO_TAG_PROMPT.format(
                    vibe=vibe, topics=topics, behaviour_profile=behaviour,
                    memory=memory, emotional_state=e_state, emotional_word=e_word,
                    specific_context=data.get("specific_context", ""),
                    mod_warning=mod_warning, safety=SAFETY_INSTRUCTIONS,
                    bot_history=bot_history, recent_messages=recent_msgs,
                    last_bot_messages=last_bot_msgs, lang=config["lang"]
                )
            else:
                style_samples = random.sample(config["questions"], min(3, len(config["questions"])))
                style_examples_str = " | ".join(style_samples)
                base_prompt = GENERAL_NO_TAG_PROMPT.format(
                    vibe=vibe, topics=topics, behaviour_profile=behaviour,
                    memory=memory, emotional_state=e_state, emotional_word=e_word,
                    mod_warning=mod_warning, safety=SAFETY_INSTRUCTIONS,
                    style_examples=style_examples_str,
                    bot_history=bot_history, recent_messages=recent_msgs,
                    last_bot_messages=last_bot_msgs, lang=config["lang"]
                )
            
            user_prompt = avoid_block + base_prompt + global_uniqueness_instruction
            # High temp for creativity
            ai_temperature = 0.7

        else:
            return jsonify({"error": "Invalid action"}), 400

        output = ""
        used_api = "none"
        used_model = "none"
        
        # Model name for tracking
        selected_model = "gemini"
        
        # ========================================================================
        # RETRY LOOP: WRAP API CALLS AND CHECK FOR BOT MENTIONS (MAX 3 ATTEMPTS)
        # ========================================================================
        max_retries = 3
        loop_count = 1 if action in ["analyze", "summarize"] else max_retries
        judge_feedback = ""

        for attempt in range(loop_count):
            current_user_prompt = user_prompt + judge_feedback
            api_success = False
            
            # 🚥 GLOBALLY RATE-LIMIT API CALLS TO PREVENT 429 HAMMERING 🚥
            while True:
                with API_CALL_LOCK:
                    if CURRENT_API_CALLS < MAX_CONCURRENT_API_CALLS:
                        CURRENT_API_CALLS += 1
                        break
                await asyncio.sleep(0.3) # Wait briefly for a slot to open up

            try:
                # --- 1. USE MAIN GEMINI API ---
                try:
                    # Combine system instruction and user prompt for Gemini
                    full_prompt = f"{system_instruction}\n\n{current_user_prompt}"
                    encoded_prompt = quote(full_prompt)
                    gemini_url = f"{GEMINI_API_BASE}?message={encoded_prompt}"
                    
                    logger.info("Calling MAIN GEMINI API for %s: %s [Active Calls: %d]", action.upper(), GEMINI_API_BASE, CURRENT_API_CALLS)
                    timeout = aiohttp.ClientTimeout(total=60)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get(gemini_url) as r:
                            if r.status == 200:
                                gemini_data = await r.json()
                                if gemini_data.get("success"):
                                    raw_output = gemini_data.get("response", "")
                                    if raw_output:
                                        output = raw_output
                                        used_api = "gemini-api"
                                        used_model = "gemini"
                                        api_success = True
                            elif r.status == 429:
                                logger.warning("Main Gemini API Status 429. Backing off...")
                                await asyncio.sleep(2.0)
                            else:
                                logger.warning("Main Gemini API Status %s", r.status)
                                await asyncio.sleep(1.0)
                except Exception as e:
                    logger.warning("Main Gemini API encountered an error: %s", e)
                
                # --- 2. TRY BACKUP VPS API IF MAIN API FAILED ---
                if not api_success:
                    logger.info("Main API failed. Calling BACKUP VPS API for %s...", action.upper())
                    try:
                        messages = []
                        if system_instruction:
                            messages.append({"role": "system", "content": system_instruction})
                        messages.append({"role": "user", "content": current_user_prompt})

                        response = await backup_client.chat.completions.create(
                            model="gemini-3-flash",
                            messages=messages,
                            stream=False, 
                        )
                        raw_output = response.choices[0].message.content
                        if raw_output:
                            output = raw_output
                            used_api = "vps-backup-api"
                            used_model = "gemini-3-flash"
                            api_success = True
                    except Exception as backup_e:
                        logger.warning("Backup VPS API failed: %s", backup_e)
                        await asyncio.sleep(1.0)

            finally:
                # Always release the concurrency lock
                with API_CALL_LOCK:
                    CURRENT_API_CALLS -= 1

            # If both APIs failed, handle retry
            if not output:
                if attempt == loop_count - 1:
                    return jsonify({"error": "All Inference APIs (Main & Backup) failed"}), 500
                continue
            
            # ========================================================================
            
            output = str(output).strip()

            # ================== ANALYSIS ENDPOINT: RETURN DIRECTLY, NO PROCESSING ==================
            if action == "analyze":
                # Populate cache and return immediately - NO JUDGE LOGIC, NO PROCESSING
                with CACHE_LOCK:
                    ANALYSIS_CACHE[country_code] = {
                        "timestamp": time.time(),
                        "data": {"response": output, "source": used_api, "model": used_model}
                    }
                return jsonify({"raw": {"response": output, "source": used_api, "model": used_model}}), 200
            # =========================================================================================

            # ================== NEW: SUMMARIZE ENDPOINT: PROCESS AND RETURN ==================
            if action == "summarize":
                # Clean up the output - remove markdown code blocks if present
                cleaned_output = output
                cleaned_output = re.sub(r"```json\s*", "", cleaned_output)
                cleaned_output = re.sub(r"
```\s*", "", cleaned_output)
                cleaned_output = cleaned_output.strip()
                
                # Try to extract JSON if there's extra text
                try:
                    # Find JSON object in the output
                    first_brace = cleaned_output.find('{')
                    last_brace = cleaned_output.rfind('}')
                    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                        cleaned_output = cleaned_output[first_brace:last_brace + 1]
                    
                    # Validate it's valid JSON
                    json.loads(cleaned_output)
                    final_output = cleaned_output
                except json.JSONDecodeError as e:
                    logger.warning("Summary output is not valid JSON, returning raw output: %s", e)
                    final_output = output
                
                # Populate cache and return
                with SUMMARY_LOCK:
                    SUMMARY_CACHE[user] = {
                        "timestamp": time.time(),
                        "data": {"response": final_output, "source": used_api, "model": used_model}
                    }
                
                logger.info("Generated SUMMARY for %s successfully", user)
                return jsonify({"raw": {"response": final_output, "source": used_api, "model": used_model}}), 200
            # =====================================================================================

            # ================== CHAT ENDPOINT: JUDGE LOGIC ONLY FOR CHAT ==================
            if action == "chat":
                # ========================================================================
                # RIGOROUS JUDGE LOGIC
                # ========================================================================
                
                # 1. Clean formatting
                output = re.sub(r'-transitional.*?__', '', output, flags=re.DOTALL | re.IGNORECASE)
                if '-transitional' in output.lower(): output = re.sub(r'-transitional.*', '', output, flags=re.DOTALL | re.IGNORECASE)
                
                # Strip ALL remaining hallucinated HTML/Markdown tags (like blockquote, p, b, br)
                output = re.sub(r'<[^>]+>', '', output)

                output = re.sub(r"^(As an AI|I'm an AI|I am an AI|I cannot|Sorry, but|Interner Fehler).*?\s*", "", output, flags=re.I)
                output = re.sub(r'^\s*(Here is|Sure,|Okay,|I will|Response:|Reply:|Output:|Answer:|My response:|Bot:).*?(\n|$)', '', output, flags=re.I | re.MULTILINE)
                output = output.replace("```json", "").replace("```", "")
                output = re.sub(r'@\(([^)]+)\)', r'@\1', output)
                
                emoji_pattern = re.compile(u"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\u2600-\u26FF\u2700-\u27BF]+", flags=re.UNICODE)
                output = emoji_pattern.sub("", output)
                output = output.replace("\uFE0F", "").replace("/", "").replace("\\", "")

                output = re.sub(r'[.,!?;:]', '', output)

                if len(output) > 3 and output.isupper():
                    output = output.lower()

                # 2. Line Filtering
                try:
                    lines = output.splitlines()
                    filtered = []
                    for line in lines:
                        stripped = line.strip()
                        if not stripped: continue
                        if (stripped.startswith('"') and stripped.endswith('"')) or (stripped.startswith("'") and stripped.endswith("'")):
                            stripped = stripped[1:-1].strip()
                        if re.search(r'\[MODERATOR\]|\bmoderator\b|\bmod\b', stripped, flags=re.I): continue
                        if re.search(r'^\s*(System|User|Assistant|Bot|AI)[:\s]', stripped, flags=re.I): continue
                        if re.search(r'\bcommand\b', stripped, flags=re.I) and re.search(r'\b(last night|yesterday|today)\b', stripped, flags=re.I): continue
                        if "thinking process" in stripped.lower() or "thought:" in stripped.lower(): continue
                        if "interner fehler" in stripped.lower(): continue
                        filtered.append(stripped)
                    output = "\n".join(filtered).strip()
                except Exception:
                    pass
                
                if len(output) > 200: output = output[:197] + "..."

                # ========================================================================
                # CHECK: PREVENT ANALYSIS DATA / ERRORS IN CHAT
                # ========================================================================
                analysis_patterns = [
                    r'\{.*\}', # JSON objects
                    r'\[.*\]', # JSON arrays
                    r'"vibe"\s*:', r'"topics"\s*:', r'"userInterest"', # Analysis keys
                    r'"relationshipState"', r'"behaviourProfile"', r'"contextMemoryBlob"',
                    r'^\s*vibe\s*:', r'^\s*topics\s*:', # Loose JSON-like
                    r'\berror\b', r'\bexception\b', r'\btraceback\b', r'\bfailed\b', r'\bunauthorized\b' # Errors
                ]
                is_invalid_format = False
                for pat in analysis_patterns:
                    if re.search(pat, output, flags=re.I):
                        logger.warning("Judge DETECTED ANALYSIS/ERROR OUTPUT ('%s'). REGENERATING...", output[:50])
                        judge_feedback = "\nSYSTEM ALERT: Do not output JSON, analysis data, or error logs. You are a human in a chat. Generate a casual chat message."
                        is_invalid_format = True
                        output = ""
                        break
                
                if is_invalid_format and attempt < loop_count - 1:
                    await asyncio.sleep(1.0)
                    continue
                # ========================================================================

                # 3. Script Check
                latin_script_countries = ["in", "pk", "ph", "id", "vn", "tr", "de", "us", "uk", "en", "pt", "es", "fi", "ng", "no", "pl"]
                bad_scripts_regex = r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\u0900-\u097F\u0980-\u09FF\u0400-\u04FF\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF\uAC00-\uD7AF\u0E00-\u0E7F]'
                
                if country_code in latin_script_countries:
                    if re.search(bad_scripts_regex, output):
                        logger.warning("Judge DETECTED LANGUAGE SWITCH. REGENERATING...")
                        judge_feedback = f"\nSYSTEM ALERT: You just used a foreign script. Write ONLY in the Latin/English alphabet."
                        output = "" 

                # 4. Forbidden Content Check
                forbidden_patterns = [
                    r'\b(politics|religion|god|allah|jesus|trump|biden|putin|ukraine|war|government|vote|election|church|mosque|temple)\b',
                    r'\b(twitch|kick\.com|streamer|trainwreck|roshtein|adin|xqc)\b',
                    r'\b(tip me|give me|loan|borrow|rain|beg|charity|donation)\b',
                    r'\b(dm me|dm for|selling|buying|trading|discount|crypto|service|script|bot|code)\b',
                    r'(http|https|www\.|t\.me|discord)',
                ]
                rules_violation = False
                for pat in forbidden_patterns:
                    if re.search(pat, output, flags=re.I):
                        logger.warning("Judge DETECTED FORBIDDEN CONTENT. REGENERATING...")
                        judge_feedback = f"\nSYSTEM ALERT: Your previous message violated chat rules (Politics/Religion/Selling/Links). Generate a safe, casual gambling chat message instead."
                        output = ""
                        rules_violation = True
                        break
                
                if rules_violation and attempt < loop_count - 1:
                    await asyncio.sleep(1.0)
                    continue

                # 5. Nonsense Check
                is_nonsense = False
                valid_short = ['lol', 'gg', 'rip', 'yo', 'f', 'w', 'l']
                if len(output) < 2 and output.lower() not in valid_short: is_nonsense = True
                if len(output) > 4 and len(set(output)) == 1: is_nonsense = True
                if not re.sub(r'[!?.,]', '', output).strip(): is_nonsense = True
                if is_nonsense:
                    output = ""

                # 6. Bot Mention Check
                bot_found = False
                if active_usernames and output:
                    for active_bot in active_usernames:
                        check_name = active_bot.lstrip("@").lower()
                        if check_name in output.lower():
                            logger.warning("Judge DETECTED bot interaction with %s. REGENERATING...", active_bot)
                            judge_feedback = f"\nSYSTEM ALERT: You just tried to mention {active_bot}. THIS IS A BOT. DO NOT MENTION THEM. Generate a completely different message."
                            bot_found = True
                            output = ""
                            break
                if bot_found and attempt < loop_count - 1:
                    await asyncio.sleep(1.0)
                    continue

                # 7. SIMILARITY CHECK (Lowered threshold from 0.8 to 0.7 for stricter checking)
                is_duplicate = False
                if output:
                    for old_msg in list(GLOBAL_BOT_HISTORY):
                        ratio = difflib.SequenceMatcher(None, output.lower(), old_msg.lower()).ratio()
                        if ratio > 0.7:  # Lowered from 0.8
                            logger.warning("Judge DETECTED SIMILARITY (Ratio: %.2f) to old message: '%s'. REGENERATING...", ratio, old_msg)
                            judge_feedback = f"\nSYSTEM ALERT: You just said '{output}', which is too similar to a recent message. Say something COMPLETELY DIFFERENT with different words and a different topic."
                            is_duplicate = True
                            output = ""
                            break
                if is_duplicate and attempt < loop_count - 1:
                    await asyncio.sleep(1.0)
                    continue

                # 8. TOPIC STAGNATION CHECK - Detect if stuck on "loss" theme
                loss_keywords = ['loss', 'lost', 'lose', 'losing', 'broke', 'bancrot', 'zero', 'rungkad', 'olats', 
                                 'thua', 'härviö', 'perdi', 'khasirt', 'fail', 'dead', 'rip', 'skinned', 'battu',
                                 'gone', 'down bad', 'liquidated', 'rekt', 'wiped']
                stuck_on_loss = False
                if output:
                    output_lower = output.lower()
                    loss_count = sum(1 for kw in loss_keywords if kw in output_lower)
                    if loss_count > 0:
                        # Check recent history for loss themes
                        recent_loss_count = 0
                        for old_msg in list(GLOBAL_BOT_HISTORY)[-5:]:  # Last 5 messages
                            old_lower = old_msg.lower()
                            recent_loss_count += sum(1 for kw in loss_keywords if kw in old_lower)
                        
                        if recent_loss_count >= 2:  # If 2+ recent messages about loss
                            logger.warning("Judge DETECTED TOPIC STAGNATION on loss theme. REGENERATING...")
                            judge_feedback = "\nSYSTEM ALERT: You've been talking about losing too much. CHANGE THE TOPIC COMPLETELY. Talk about games, luck, the site, ask a question, or make a random observation. NO MORE LOSS COMPLAINTS."
                            stuck_on_loss = True
                            output = ""
                
                if stuck_on_loss and attempt < loop_count - 1:
                    await asyncio.sleep(1.0)
                    continue

                # 9. WORD REPETITION CHECK - Check if same words repeated
                if output:
                    words = output.lower().split()
                    if len(words) >= 2:
                        word_counts = {}
                        for word in words:
                            word_counts[word] = word_counts.get(word, 0) + 1
                        # If any word appears 3+ times in a short message
                        repeated_word = False
                        for word, count in word_counts.items():
                            if count >= 3 and len(word) > 2:
                                logger.warning("Judge DETECTED WORD REPETITION: '%s' appears %d times. REGENERATING...", word, count)
                                judge_feedback = f"\nSYSTEM ALERT: You repeated the word '{word}' too many times. Generate a natural, varied message."
                                repeated_word = True
                                output = ""
                                break
                        if repeated_word and attempt < loop_count - 1:
                            await asyncio.sleep(1.0)
                            continue

                if output:
                    GLOBAL_BOT_HISTORY.append(output)
                    break

        return jsonify({"raw": {"response": output, "source": used_api, "model": used_model}}), 200

    except Exception as e:
        logger.exception("Inference API failure")
        return jsonify({"error": "Inference API failure", "details": str(e)}), 500

    finally:
        # ALWAYS release the "stampede lock" when the fetch finishes (success or crash)
        if action == "analyze":
            with CACHE_LOCK:
                if country_code in ANALYSIS_IN_PROGRESS:
                    del ANALYSIS_IN_PROGRESS[country_code]
        
        # NEW: Release summary lock
        if action == "summarize":
            with SUMMARY_LOCK:
                if user in SUMMARY_IN_PROGRESS:
                    del SUMMARY_IN_PROGRESS[user]

@app.route("/", methods=["GET"])
def home():
    return "Server Active. Use country codes like /us, /in, /pk, /de for API access."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
