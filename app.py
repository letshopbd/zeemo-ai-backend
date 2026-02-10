import os
import json
import datetime
import time
import asyncio
from flask import Flask, request, jsonify, send_file
from groq import Groq
from tavily import TavilyClient
import edge_tts
import re
from pydub import AudioSegment

app = Flask(__name__)

# --- CONFIGURATION ---
# [FIX] Render এবং Linux সার্ভারের জন্য ফাইল পাথ '/tmp' ফোল্ডারে দেওয়া হলো
# কারণ Render-এ মেইন ফোল্ডারে ফাইল সেভ করার পারমিশন থাকে না।
AUDIO_FILE = "/tmp/response.mp3"
PCM_FILE = "/tmp/response_pcm.wav"
MEMORY_FILE = "/tmp/memory.json"

# [FIX] API Key সরাসরি কোডে না লিখে environment variable থেকে নেওয়া হচ্ছে
# এটি GitHub Security Alert সমাধান করবে।
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY") 

VOICE_NAME = "en-US-AnaNeural"

# API Clients Initialization
# Key না থাকলে যাতে সার্ভার ক্র্যাশ না করে, তাই চেক রাখা হলো
if not GROQ_API_KEY:
    print("⚠️ WARNING: GROQ_API_KEY not found in environment variables!")
if not TAVILY_API_KEY:
    print("⚠️ WARNING: TAVILY_API_KEY not found in environment variables!")

client = Groq(api_key=GROQ_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# --- MEMORY MANAGEMENT ---
def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_memory(history):
    try:
        with open(MEMORY_FILE, 'w') as f:
            json.dump(history[-20:], f, indent=2)
    except Exception as e:
        print(f"❌ Memory Save Error: {e}")

# --- WEB SEARCH TOOL ---
def search_web(query):
    print(f"🔎 Tavily Searching: {query}")
    try:
        response = tavily.search(query=query, search_depth="basic", max_results=3)
        results = response.get("results", [])
        if results:
            summary = ""
            for r in results:
                summary += f"- {r['title']}: {r['content']}\n"
            return summary.strip()
        return "No results found."
    except Exception as e:
        print(f"❌ Search Error: {e}")
        return "Search failed."

# --- AUDIO GENERATION & CONVERSION ---
async def generate_speech(text, emotion):
    print("🔊 Generating Audio...")
    
    # 1. Generate MP3 with EdgeTTS
    try:
        communicate = edge_tts.Communicate(text, VOICE_NAME)
        await communicate.save(AUDIO_FILE)
    except Exception as e:
        print(f"❌ EdgeTTS Error: {e}")
        return

    # 2. Convert MP3 to WAV (PCM) for ESP32
    # ESP32 needs: 16000Hz, Mono, 16-bit PCM
    try:
        # Dockerfile এ ffmpeg ইনস্টল করা থাকলে pydub অটোমেটিক ডিটেক্ট করবে
        sound = AudioSegment.from_mp3(AUDIO_FILE)
        sound = sound.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        sound.export(PCM_FILE, format="wav")
        print(f"✅ Converted to WAV: {PCM_FILE}")
    except Exception as e:
        print(f"❌ Audio Conversion Error: {e}")
        print("💡 Hint: Ensure 'ffmpeg' is installed in Dockerfile.")

def clean_text_for_tts(text):
    # Remove markdown links, URLs, and asterisks
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'http[s]?://\S+', '', text)
    text = re.sub(r'www\.\S+', '', text)
    text = re.sub(r'\*.*?\*', '', text) 
    return text.strip()

# --- ROUTES ---
@app.route('/')
def home():
    return "Zeemo AI Backend is Running! 🚀", 200

@app.route('/audio')
def get_audio():
    # ESP32 will request this URL
    try:
        if os.path.exists(PCM_FILE):
            return send_file(PCM_FILE, mimetype="audio/wav")
        elif os.path.exists(AUDIO_FILE):
            # Fallback to MP3 if conversion failed
            return send_file(AUDIO_FILE, mimetype="audio/mpeg")
        else:
            return "No audio generated yet.", 404
    except Exception as e:
        return str(e), 500

# --- EMOTION DETECTION ---
def determine_emotion(text):
    text = text.lower()
    if any(w in text for w in ["wink", ";)", "😉"]): return "wink"
    if any(w in text for w in ["sleep", "goodnight", "bye", "rest", "tired", "bed"]): return "sleep"
    if any(w in text for w in ["haha", "lol", "happy", "glad", "yay", "love", "fun", "great", "laugh", "smile"]): return "happy"
    if any(w in text for w in ["sad", "sorry", "unfortunately", "bad", "cry", "miss", "grief"]): return "sad"
    if any(w in text for w in ["wow", "really", "amazing", "!", "oh my", "surprise"]): return "surprised"
    if any(w in text for w in ["umm", "hmm", "thinking", "wait", "let me see"]): return "thinking"
    return "neutral"

# --- CHAT ENDPOINT ---
@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_msg = data.get('message', '')
    if not user_msg: return jsonify({"error": "No message provided"}), 400

    print(f"user: {user_msg}")
    history = load_memory()
    
    messages = [
        {"role": "system", "content": (
            "You are Zeemo, a helpful, witty, and 'all-knowing' AI assistant created by S. M. Tamzid Huda and Abu Sayem Jarif. "
            "You have a long-term memory of previous conversations. "
            "Current Date: " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ". "
            "IMPORTANT: Act like a real human. Use filler words naturally (e.g., 'Umm', 'Ah!', 'Oh wow', 'Hmm', 'Haha'). "
            "Be emotional and expressive. "
            "CRITICAL RULES: \n"
            "1. DO NOT descibe actions in text like *laughs* or *smiles*. Just say the words.\n"
            "2. If something is funny, just say 'Haha'.\n"
            "3. Keep answers concise but very human."
        )}
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": user_msg})

    try:
        # Web Search Logic
        search_triggers = [
            'weather', 'price', 'score', 'news', 'current', 'today', 'latest',
            'who', 'what', 'where', 'when', 'advisor', 'minister', 'president', 
            'bangladesh', 'dhaka', 'result', 'winner', 'live'
        ]
        
        # Check if search is needed
        if any(word in user_msg.lower() for word in search_triggers):
            search_result = search_web(user_msg)
            messages[-1]["content"] += f"\n[SYSTEM: Real-time Search Results]\n{search_result}\n"

        # LLM Call
        chat_completion = client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=500
        )

        ai_response_raw = chat_completion.choices[0].message.content
        
        # Cleanup Text
        ai_response = re.sub(r'\*.*?\*', '', ai_response_raw).strip()
        ai_response = re.sub(r'\s+', ' ', ai_response)

        # Save Memory
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": ai_response})
        save_memory(history)
        
        print(f"AI: {ai_response}")
        emotion = determine_emotion(ai_response_raw) 
        print(f"Emotion: {emotion}")

        # TTS & Conversion
        tts_text = clean_text_for_tts(ai_response)
        
        # Generate Audio
        asyncio.run(generate_speech(tts_text, emotion))
        
        # Prepare Response URL
        # Render HTTPS URLs automatically handles port mapping
        audio_url = f"{request.host_url}audio?t={int(time.time())}"
        
        words = len(ai_response.split())
        duration_ms = int((words / 2.5) * 1000) + 1000 

        return jsonify({
            "response": ai_response, 
            "audio_url": audio_url, 
            "emotion": emotion,
            "duration": duration_ms
        })

    except Exception as e:
        print(f"Server Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Render বা Docker এ পোর্ট এনভায়রনমেন্ট থেকে নেওয়া ভালো, না থাকলে 10000
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)