# app.py — Smart Learning Voice Assistant v2 (Flask + Twilio + Gemini)

import os
import re
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather
from google import genai
from dashboard import read_prompt, bp as dashboard_bp

# ---------------------------------------------
# Flask + Logging setup
# ---------------------------------------------
app = Flask(__name__)

LOG_FILE = "app.log"
handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=2)
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)

logging.basicConfig(level=logging.INFO)

# ---------------------------------------------
# Global runtime configuration
# ---------------------------------------------
MODEL_NAME = "gemma-3-27b-it"        # Gemma 27B
global_api_key = None                # Will be set at startup by user input

# Register dashboard blueprint
app.register_blueprint(dashboard_bp)

# ---------------------------------------------
# Helper: Gemini Client
# ---------------------------------------------
def get_genai_client():
    if not global_api_key:
        raise RuntimeError("Gemini API key is missing. Please restart and input it.")
    return genai.Client(api_key=global_api_key)

# ---------------------------------------------
# Helper: Ask the AI Teacher
# ---------------------------------------------
def ask_teacher(prompt: str) -> str:
    try:
        client = get_genai_client()
        resp = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        if not resp or not getattr(resp, "text", None):
            raise RuntimeError("Empty response from Gemini.")
        return resp.text.strip()
    except Exception as e:
        logging.exception("Gemini API call failed: %s", e)
        return None

# ---------------------------------------------
# Helper: Text-to-speech pacing
# ---------------------------------------------
def tts_speak(resp: VoiceResponse, text: str):
    """Speak text slowly and clearly with pauses between sentences."""
    text = re.sub(r"\s+", " ", text)
    sentences = re.split(r"(?<=[.!?]) +", text)
    for s in sentences:
        if s.strip():
            resp.say(s.strip(), voice="alice", language="en-US")
            resp.pause(length=1.0)

# ---------------------------------------------
# Helper: Follow-up prompt
# ---------------------------------------------
def ask_follow_up(resp: VoiceResponse, prompt_msg="Would you like to ask another question?"):
    gather = Gather(
        input="speech",
        action="/gather_followup",
        method="POST",
        timeout=5,
        speech_timeout="auto"
    )
    gather.say(prompt_msg, voice="alice", language="en-US")
    resp.append(gather)
    resp.say("Goodbye for now!", voice="alice")
    resp.hangup()

# ---------------------------------------------
# Route: Initial call
# ---------------------------------------------
@app.route("/", methods=["GET", "POST"])
def inbound_call():
    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/gather_response",
        method="POST",
        timeout=5,
        speech_timeout="auto"
    )
    gather.say(
        "Hello again! I’m your learning assistant teacher. "
        "Ask your question now.",
        voice="alice", language="en-US"
    )

    resp.append(gather)
    resp.say("I didn’t hear a question. Goodbye!", voice="alice")
    resp.hangup()
    return str(resp)

# ---------------------------------------------
# Route: Handle the student's first question
# ---------------------------------------------
@app.route("/gather_response", methods=["POST"])
def gather_response():
    speech_text = (request.values.get("SpeechResult") or "").strip()
    resp = VoiceResponse()

    if not speech_text:
        resp.say("Sorry, I didn’t catch that.", voice="alice")
        ask_follow_up(resp)
        return str(resp)

    logging.info(f"Student asked: {speech_text}")

    # Friendly "thinking" feedback
    resp.say("Hmm, let me think for a second.", voice="alice")
    resp.pause(length=1.2)

    base_prompt = read_prompt() or (
        "You are a kind, encouraging teacher speaking to a young student over the phone. "
        "Explain concepts clearly and slowly in one or two short sentences. "
        "Avoid long words. End with a gentle encouragement like 'Good job!' or 'Keep learning!'."
    )

    prompt = f"{base_prompt} Student asked: \"{speech_text}\""

    answer = ask_teacher(prompt)
    if not answer:
        resp.say("Sorry, I’m having trouble getting the answer right now.", voice="alice")
        ask_follow_up(resp)
        return str(resp)

    resp.say("Here’s what I found:", voice="alice")
    resp.pause(length=1.0)
    tts_speak(resp, answer)
    ask_follow_up(resp)
    return str(resp)

# ---------------------------------------------
# Route: Handle follow-up question
# ---------------------------------------------
@app.route("/gather_followup", methods=["POST"])
def gather_followup():
    speech_text = (request.values.get("SpeechResult") or "").lower().strip()
    resp = VoiceResponse()

    if any(phrase in speech_text for phrase in ["no", "nope", "nothing", "bye"]):
        resp.say("Okay! Goodbye and keep learning!", voice="alice")
        resp.hangup()
        return str(resp)

    if not speech_text:
        resp.say("I didn’t catch that. Let’s stop here for now. Goodbye!", voice="alice")
        resp.hangup()
        return str(resp)

    logging.info(f"Follow-up question: {speech_text}")

    # Friendly "thinking" feedback for follow-ups
    resp.say("Hmm, let me think about that question too.", voice="alice")
    resp.pause(length=1.2)

    prompt = (
        "Continue acting as a friendly teacher. "
        "Give a short, clear spoken answer, two sentences maximum. "
        f"Student asked: \"{speech_text}\""
    )

    answer = ask_teacher(prompt)
    if not answer:
        resp.say("Sorry, I can’t reach the teacher service right now.", voice="alice")
        ask_follow_up(resp)
        return str(resp)

    resp.say("Here’s another explanation:", voice="alice")
    resp.pause(length=1.0)
    tts_speak(resp, answer)
    ask_follow_up(resp)
    return str(resp)

# ---------------------------------------------
# Application Entry Point (persistent API key)
# ---------------------------------------------
def load_api_key():
    """Load the Gemini API key from key.txt, or ask the user if missing."""
    key_file = "key.txt"

    # --- START OF NEW CODE ---
    # 1. Check environment variable first, which is set in Colab
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key:
        logging.info("✅ Gemini API key loaded from environment variable")
        return env_key
    # --- END OF NEW CODE ---

    if os.path.exists(key_file):
        with open(key_file, "r") as f:
            api_key = f.read().strip()
            if api_key:
                logging.info("✅ Gemini API key loaded from key.txt")
                return api_key

    # If file missing or empty, ask user
    api_key = input("🔑 Enter your Gemini API key: ").strip()
    if not api_key:
        logging.error("❌ API key not provided. Exiting.")
        exit(1)

    # Save key for next run
    with open(key_file, "w") as f:
        f.write(api_key)
    logging.info("✅ Gemini API key saved to key.txt")

    return api_key


if __name__ == "__main__":
    try:
        # Assign directly; no global statement needed at top-level
        global_api_key = load_api_key()
    except Exception as e:
        logging.exception("Error while loading API key.")
        exit(1)

    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
