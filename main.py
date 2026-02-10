import os
import random
import logging
import json
import re
import asyncio
import aiohttp
import difflib
from flask import Flask, request, jsonify
from urllib.parse import urlparse, quote
from collections import deque

# ================== LOGGING ===================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("CHAT-FARMER")
# ==============================================

app = Flask(__name__)

# ================== API CONFIGURATION ===================
# New Primary API Base
NEW_API_BASE = "http://104.168.62.69:8000/ai"

# Backup API (Copilot)
BACKUP_API_BASE = "https://copilot-ai-two.vercel.app" 

# Model Configurations
ANALYSIS_TIER_1 = [
    "sonar-reasoning",
    "deepseek-r1-0528",
    "deepseek-r1-distill-qwen-14b",
    "qwen-3-235b",
    "gpt-5.2"
]

CHAT_TIER_1 = [
    "gemini-2.5-flash",
    "gemini-3-flash",
    "mistral-small-3.1-24b",
    "command-r",
    "llama-3.3-70b-versatile"
]

# Global History to prevent swarm repetition (Last 20 messages across ALL users)
GLOBAL_BOT_HISTORY = deque(maxlen=20)
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
            "yo any huge wins?", "rip my balance lol", "site is so dry rn", 
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
- If you are losing, sound tilted/annoyed. If winning, flex a little but don't look like a bot.
- STRICT RULE: Use ONLY the standard characters for your language. Do NOT switch scripts.
- STRICT RULE: NO POLITICS, NO RELIGION, NO STREAMERS.
- ANTI-FARMING: Don't just ask "how are you". Talk about luck, the game, or money.

IMPORTANT: You MUST speak in {lang}. Do not sound like a customer support agent. Be a degenerate gambler.
"""


ANALYSIS_PROMPT = """
You are analyzing a casino chat to understand the social dynamics.
Your username is {username}.

Based on these recent chat messages:
{recent_messages}

And your bot's recent messages:
{bot_messages}

IMPORTANT: ONLY RETURN A SINGLE VALID JSON OBJECT. DO NOT INCLUDE ANY MARKDOWN, CODE-FENCES (```), OR ANY EXPLANATORY TEXT.
START IMMEDIATELY WITH THE JSON OBJECT (the very first character MUST be '{{').

Your JSON must match this structure exactly:
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

Focus on accuracy and brevity.
ONLY return valid JSON.
"""

INACTIVITY_PROMPT = """
{persona}
Current chat context:
- Vibe: {vibe}
- Topics: {topics}
- Your behavior profile: {behaviour_profile}
- Memory: {memory}
- Your emotional state: {emotional_state} ({emotional_word})
{mod_warning}
{safety}

The chat is dead. Send a message to wake it up, but DO NOT sound like a "farming bot".
- BAD: "Hello everyone", "How are you", "Any winners?"
- GOOD: Complain about a loss, mention a specific game, or make a random observation about luck.
- Keep it lowercase and short (max 8 words).
- Use slang.
Language: {lang}

Here are your previous messages for context:
{bot_history}

IMPORTANT: DO NOT REPEAT any of these messages you've sent before:
{last_bot_messages}

Your response:
"""

MENTION_PROMPT = """
{persona}
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
- Tag them with @username (NO parentheses).
- If [MODERATOR] is present, be polite but short.
- If multiple people tagged you, pick the most interesting one to reply to (don't spam 3 messages).
- Act like a real human: intentionally ignore punctuation.
- Don't use emojies excessively (max 1).
- Keep it very short - maximum 6 words.
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
{persona}
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
- Tag them with @username (no parentheses).
- ONLY reply if their message is interesting. If they just said "hi", say something cool back or ignore it.
- Do NOT sound like a support bot. Be casual.
- Maximum 5-9 words only.
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
{persona}
Current chat context:
- Vibe: {vibe}
- Topics: {topics}
- Your behavior profile: {behaviour_profile}
- Memory: {memory}
- Your emotional state: {emotional_state} ({emotional_word})
{mod_warning}
{safety}

Say something to the chat without tagging anyone.
- It must fit the current vibe (if people are angry, don't be happy).
- Avoid generic questions like "how is everyone". 
- Instead: React to the "site luck", a specific game, or your own balance.
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
        active_url = "https://farmer-auth1-a6807b536c38.herokuapp.com/active_users"
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
        auth_url = f"https://farmer-auth1-a6807b536c38.herokuapp.com/check?user={encoded_user}"
        
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


    final_prompt = ""
    
    persona_filled = PERSONA_TEMPLATE.format(
        lang=config["lang"],
        vibe=config["vibe"],
        username=user
    )

    # ----------------- fetch active users and build avoid block -----------------
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
    # ---------------------------------------------------------------------------

    # ----------------- Global History Injection (Similarity Check API) -------------
    # We inject the global history into the prompt so the model (API) acts as the judge
    # and ensures the new output is unique compared to the swarm's recent activity.
    global_context_msgs = " | ".join(list(GLOBAL_BOT_HISTORY))
    global_uniqueness_instruction = ""
    if global_context_msgs:
        global_uniqueness_instruction = (
            f"\n\nGLOBAL SWARM HISTORY (DO NOT REPEAT OR SOUND LIKE THESE):"
            f"\n[{global_context_msgs}]\n"
            f"Ensure your response is distinct from the text above."
        )
    # ---------------------------------------------------------------------------

    if action == "analyze":
        final_prompt = avoid_block + ANALYSIS_PROMPT.format(
            username=user,
            recent_messages=data.get("recent_messages", ""),
            bot_messages=data.get("bot_messages", "")
        )

    elif action == "chat":
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
                persona=persona_filled, vibe=vibe, topics=topics, behaviour_profile=behaviour,
                memory=memory, emotional_state=e_state, emotional_word=e_word,
                mod_warning=mod_warning, safety=SAFETY_INSTRUCTIONS,
                bot_history=bot_history, last_bot_messages=last_bot_msgs, lang=config["lang"]
            )
        elif mode == "mention":
            base_prompt = MENTION_PROMPT.format(
                persona=persona_filled, vibe=vibe, topics=topics, behaviour_profile=behaviour,
                memory=memory, emotional_state=e_state, emotional_word=e_word,
                specific_context=data.get("specific_context", ""),
                mod_warning=mod_warning, safety=SAFETY_INSTRUCTIONS,
                bot_history=bot_history, recent_messages=recent_msgs,
                last_bot_messages=last_bot_msgs, lang=config["lang"]
            )
        elif mode == "general_tag":
            base_prompt = GENERAL_TAG_PROMPT.format(
                persona=persona_filled, vibe=vibe, topics=topics, behaviour_profile=behaviour,
                memory=memory, emotional_state=e_state, emotional_word=e_word,
                mod_warning=mod_warning, safety=SAFETY_INSTRUCTIONS,
                active_users_list=avoid_block,
                bot_history=bot_history, recent_messages=recent_msgs,
                last_bot_messages=last_bot_msgs, lang=config["lang"]
            )
        else:
            style_samples = random.sample(config["questions"], min(3, len(config["questions"])))
            style_examples_str = " | ".join(style_samples)
            base_prompt = GENERAL_NO_TAG_PROMPT.format(
                persona=persona_filled, vibe=vibe, topics=topics, behaviour_profile=behaviour,
                memory=memory, emotional_state=e_state, emotional_word=e_word,
                mod_warning=mod_warning, safety=SAFETY_INSTRUCTIONS,
                style_examples=style_examples_str,
                bot_history=bot_history, recent_messages=recent_msgs,
                last_bot_messages=last_bot_msgs, lang=config["lang"]
            )
        
        final_prompt = avoid_block + base_prompt + global_uniqueness_instruction

    else:
        return jsonify({"error": "Invalid action"}), 400


    try:
        output = ""
        used_api = "none"
        used_model = "none"
        
        # Determine Model Tier
        model_tier = ANALYSIS_TIER_1 if action == "analyze" else CHAT_TIER_1
        
        # ========================================================================
        # RETRY LOOP: WRAP API CALLS AND CHECK FOR BOT MENTIONS (MAX 3 ATTEMPTS)
        # ========================================================================
        max_retries = 3
        loop_count = 1 if action == "analyze" else max_retries

        for attempt in range(loop_count):
            
            # --- ATTEMPT NEW API TIER LIST FIRST ---
            success_new_api = False
            
            # Randomize model order slightly to distribute load, but keep tier logic
            current_tier = model_tier.copy()
            # We don't want to try ALL models in one attempt loop because that takes too long.
            # We try 2 models per attempt.
            selected_models = random.sample(current_tier, min(2, len(current_tier)))

            for model_name in selected_models:
                try:
                    api_url = f"{NEW_API_BASE}?q={quote(final_prompt)}&model={model_name}"
                    logger.info("Calling NEW API: %s (Model: %s)", NEW_API_BASE, model_name)
                    
                    timeout = aiohttp.ClientTimeout(total=8) # Fast timeout for main API
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get(api_url) as r:
                            r.raise_for_status()
                            ai_data = await r.json()
                            
                            # Check success flag from new API
                            if ai_data.get("success") is True:
                                raw_output = ai_data.get("response", "")
                                if raw_output:
                                    output = raw_output
                                    used_api = "new-api"
                                    used_model = model_name
                                    success_new_api = True
                                    break
                except Exception as e:
                    logger.warning("New API model %s failed: %s", model_name, e)
                    continue # Try next model
            
            # --- FALLBACK TO COPILOT IF NEW API FAILED ---
            if not success_new_api:
                try:
                    api_mode = "smart" if action == "analyze" else "chat"
                    api_url = f"{BACKUP_API_BASE.rstrip('/')}/{api_mode}"
                    logger.info("Fallback to BACKUP API (Copilot): %s", api_url)
                    
                    params = {"prompt": final_prompt}
                    timeout = aiohttp.ClientTimeout(total=15)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get(api_url, params=params) as r:
                            r.raise_for_status()
                            ai_data = await r.json()
                            output = ai_data.get("response") or ai_data.get("message") or ai_data.get("content") or ""
                            
                            if output and "no response" not in str(output).lower():
                                used_api = "backup-copilot"
                                used_model = "copilot"
                            else:
                                output = ""
                except Exception as e:
                    logger.error("Backup API failed: %s", e)
                    if attempt == loop_count - 1:
                        return jsonify({"error": "All Inference APIs failed"}), 500

            # ========================================================================
            
            output = str(output).strip()

            if action == "chat":
                # ========================================================================
                # RIGOROUS JUDGE LOGIC
                # ========================================================================
                
                # 1. Clean formatting
                output = re.sub(r'<think>.*?</think>', '', output, flags=re.DOTALL | re.IGNORECASE)
                if '<think>' in output.lower(): output = re.sub(r'<think>.*', '', output, flags=re.DOTALL | re.IGNORECASE)
                output = re.sub(r"^(As an AI|I'm an AI|I am an AI|I cannot|Sorry, but|Interner Fehler).*?\s*", "", output, flags=re.I)
                output = re.sub(r'^\s*(Here is|Sure,|Okay,|I will|Response:|Reply:|Output:|Answer:|My response:|Bot:).*?(\n|$)', '', output, flags=re.I | re.MULTILINE)
                output = output.replace("```json", "").replace("```", "")
                output = re.sub(r'@\(([^)]+)\)', r'@\1', output)
                
                emoji_pattern = re.compile(u"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\u2600-\u26FF\u2700-\u27BF]+", flags=re.UNICODE)
                output = emoji_pattern.sub("", output)
                output = output.replace("\uFE0F", "").replace("/", "").replace("\\", "")

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
                        if "no response generated" in stripped.lower() or "no response from copilot" in stripped.lower(): continue
                        filtered.append(stripped)
                    output = "\n".join(filtered).strip()
                except Exception:
                    pass
                
                if len(output) > 200: output = output[:197] + "..."

                # 3. Script Check
                latin_script_countries = ["in", "pk", "ph", "id", "vn", "tr", "de", "us", "uk", "en", "pt", "es", "fi", "ng", "no", "pl"]
                bad_scripts_regex = r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\u0900-\u097F\u0980-\u09FF\u0400-\u04FF\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF\uAC00-\uD7AF\u0E00-\u0E7F]'
                
                if country_code in latin_script_countries:
                    if re.search(bad_scripts_regex, output):
                        logger.warning("Judge DETECTED LANGUAGE SWITCH. REGENERATING...")
                        final_prompt += f"\nSYSTEM ALERT: You just used a foreign script. Write ONLY in the Latin/English alphabet."
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
                        final_prompt += f"\nSYSTEM ALERT: Your previous message violated chat rules (Politics/Religion/Selling/Links). Generate a safe, casual gambling chat message instead."
                        output = ""
                        rules_violation = True
                        break
                if rules_violation and attempt < loop_count - 1: continue

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
                            final_prompt += f"\nSYSTEM ALERT: You just tried to mention {active_bot}. THIS IS A BOT. DO NOT MENTION THEM. Generate a completely different message."
                            bot_found = True
                            output = ""
                            break
                if bot_found and attempt < loop_count - 1: continue

                # 7. SIMILARITY CHECK (The "Judge API Logic" implemented via History Context + Fuzzy Match)
                # Ensure the new message isn't too similar to the Global History
                is_duplicate = False
                if output:
                    for old_msg in list(GLOBAL_BOT_HISTORY):
                        # Use difflib for similarity ratio
                        ratio = difflib.SequenceMatcher(None, output.lower(), old_msg.lower()).ratio()
                        if ratio > 0.8: # 80% similarity threshold
                            logger.warning("Judge DETECTED SIMILARITY (Ratio: %.2f) to old message: '%s'. REGENERATING...", ratio, old_msg)
                            final_prompt += f"\nSYSTEM ALERT: You just said '{output}', which is too similar to a recent message. Say something completely different."
                            is_duplicate = True
                            output = ""
                            break
                if is_duplicate and attempt < loop_count - 1: continue

                # If we have a clean output, break the retry loop
                if output:
                    # Success - Add to global history
                    GLOBAL_BOT_HISTORY.append(output)
                    break

        return jsonify({"raw": {"response": output, "source": used_api, "model": used_model}}), 200

    except Exception as e:
        logger.exception("Inference API failure")
        return jsonify({"error": "Inference API failure", "details": str(e)}), 500


@app.route("/", methods=["GET"])
def home():
    return "Server Active. Use country codes like /us, /in, /pk, /de for API access."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
