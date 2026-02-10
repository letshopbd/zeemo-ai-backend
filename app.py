import os
import json
import datetime
import time
import asyncio
from flask import Flask, request, jsonify, send_file
from groq import Groq
from tavily import TavilyClient
import edge_tts
from xml.sax.saxutils import escape
import re
from pydub import AudioSegment  # এই লাইব্রেরিটি অডিও কনভার্ট করবে

app = Flask(__name__)

# --- CONFIGURATION ---
# [FIX] বর্তমান ডিরেক্টরি সেট করা (যাতে ফাইল হারিয়ে না যায়)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GROQ_API_KEY = "gsk_yMuY........"
TAVILY_API_KEY = "tvly-........" 
MEMORY_FILE = os.path.join(BASE_DIR, "memory.json")
VOICE_NAME = "en-US-AnaNeural"

# ফাইল পাথ ফিক্স
AUDIO_FILE = os.path.join(BASE_DIR, "response.mp3")
PCM_FILE = os.path.join(BASE_DIR, "response_pcm.wav")

client = Groq(api_key=GROQ_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# --- MEMORY ---
def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_memory(history):
    with open(MEMORY_FILE, 'w') as f:
        json.dump(history[-20:], f, indent=2)

# --- TOOLS ---
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
    communicate = edge_tts.Communicate(text, VOICE_NAME)
    await communicate.save(AUDIO_FILE)
    
    # 2. Convert MP3 to WAV (PCM) for ESP32 [CRITICAL STEP]
    # ESP32 needs: 16000Hz, Mono, 16-bit PCM
    try:
        sound = AudioSegment.from_mp3(AUDIO_FILE)
        sound = sound.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        sound.export(PCM_FILE, format="wav")
        print(f"✅ Converted to WAV: {PCM_FILE}")
    except Exception as e:
        print(f"❌ Audio Conversion Error: {e}")
        print("Make sure FFmpeg is installed and added to System Path!")

def clean_text_for_tts(text):
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
            # Fallback if conversion failed
            return send_file(AUDIO_FILE, mimetype="audio/mpeg")
        else:
            return "No audio found", 404
    except Exception as e:
        return str(e), 500

# --- EMOTION ---
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
        
        # এখানে অডিও জেনারেট এবং কনভার্ট দুটোই হবে
        asyncio.run(generate_speech(tts_text, emotion))
        
        # ESP32 এর জন্য URL
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
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # 0.0.0.0 মানে সব নেটওয়ার্ক ইন্টারফেস থেকে অ্যাক্সেস করা যাবে
    app.run(host='0.0.0.0', port=5000, debug=True)