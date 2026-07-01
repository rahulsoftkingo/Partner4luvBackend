import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from typing import Optional

# Load .env file
base_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
_whisper_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None


# Whisper accepts these audio formats
ALLOWED_AUDIO_EXTENSIONS = {"mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm", "ogg"}
 
# Whisper API hard limit is 25 MB per file
MAX_AUDIO_FILE_SIZE_BYTES = 25 * 1024 * 1024

""" Generates AI-based compatibility insight between two users. """
async def generate_match_insight(user1_data: dict, user2_data: dict):
    try:
        # Safe extraction
        u1_tags = user1_data.get("tags") or []
        u2_tags = user2_data.get("tags") or []
        u1_bio = user1_data.get("bio") or ""
        u2_bio = user2_data.get("bio") or ""

        u1_tags_text = ", ".join(u1_tags) if u1_tags else "No tags"
        u2_tags_text = ", ".join(u2_tags) if u2_tags else "No tags"

        prompt = f"""
User 1:
Bio: {u1_bio}
Tags: {u1_tags_text}

User 2:
Bio: {u2_bio}
Tags: {u2_tags_text}

Analyze the compatibility between these two users for a dating application.

Evaluate the following categories:
- Strength
- Personality
- Relationship
- Lifestyle
- Values Alignment
- Interest Match
- Habit
- Final

Give each category a score from 0 to 100.

For every category, provide:
- score
- user1 insight
- user2 insight

Return ONLY valid JSON in the following format:

{{
  "overallScore": 85,
  "summary": "A short compatibility summary.",
  "breakdown": [
    {{
      "category": "Strength",
      "score": 80,
      "user1": "User 1's strengths show in one word",
      "user2": "User 2's strengths show in one word"
    }},
    {{
      "category": "Personality",
      "score": 88,
      "user1": "User 1 personality insight show in one word",
      "user2": "User 2 personality insight show in one word"
    }},
    {{
      "category": "Relationship",
      "score": 84,
      "user1": "User 1 relationship style show in one word",
      "user2": "User 2 relationship style show in one word"
    }},
    {{
      "category": "Lifestyle",
      "score": 90,
      "user1": "User 1 lifestyle show in one word",
      "user2": "User 2 lifestyle show in one word"
    }},
    {{
      "category": "Values Alignment",
      "score": 92,
      "user1": "User 1 values show in one word",
      "user2": "User 2 values show in one word"
    }},
    {{
      "category": "Interest Match",
      "score": 78,
      "user1": "User 1 interests show in one word",
      "user2": "User 2 interests show in one word"
    }},
    {{
      "category": "Habit",
      "score": 81,
      "user1": "User 1 habits show in one word",
      "user2": "User 2 habits show in one word"
    }},
    {{
      "category": "Final",
      "score": 85,
      "user1": "Overall summary for User 1 show in one word",
      "user2": "Overall summary for User 2 show in one word"
    }}
  ]
}}

Do not include markdown, explanations, or any text outside the JSON.
"""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=1000
        )

        content = response.choices[0].message.content

        if not content:
            raise ValueError("Empty response from OpenAI")

        return json.loads(content)

    except Exception as e:
        print("AI Insight Error:", str(e))

        # fallback
        return {
            "overallScore": 75,
            "summary": "You both share a balanced lifestyle and compatible interests.",
            "breakdown": [
                {"category": "Lifestyle", "score": 70},
                {"category": "Career", "score": 75},
                {"category": "Core Values", "score": 80},
                {"category": "Adventure", "score": 75}
            ]
        }


""" Simple fallback similarity score (Jaccard similarity)"""
def calculate_match_score(user1_tags: list, user2_tags: list):

    if not user1_tags or not user2_tags:
        return 50

    set1, set2 = set(user1_tags), set(user2_tags)

    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))

    if union == 0:
        return 50

    return round((intersection / union) * 100)
  
  
""" Generates AI-based dating bios and suggested tags based on user requirements. """
async def bio_generation(user_requirements: str):
    try:
        if not user_requirements.strip():
            raise ValueError("User requirements text cannot be empty")

        prompt = f"""
The user wants a dating application bio based on the following requirements:
"{user_requirements}"

Generate three distinct variations of the bio:
1. Casual & Fun (witty, lighthearted)
2. Detailed & Authentic (meaningful, expressive)
3. Short & Punchy (minimalist, engaging)

Return ONLY valid JSON in the following format:

{{
  "variations": {{
    "casual": "Text for casual bio variation...",
    "authentic": "Text for detailed/authentic bio variation...",
    "short": "Text for short/punchy bio variation..."
  }}
}}

Do not include markdown, explanations, or any text outside the JSON.
"""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=800
        )

        content = response.choices[0].message.content

        if not content:
            raise ValueError("Empty response from OpenAI")

        return json.loads(content)

    except Exception as e:
        print("Bio Generation Error:", str(e))

        # Fallback response in case of API failure
        return {
            "variations": {
                "casual": f"Living life to the fullest! Down for new adventures and great conversation. {user_requirements}",
                "authentic": f"Looking to connect with genuine people. I value honesty, good energy, and shared experiences. {user_requirements}",
                "short": f"Adventure seeker. Let's grab coffee. {user_requirements}"
            },
            "suggestedTags": ["Dating", "Lifestyle", "Connections", "Friendly", "Introvert"]
        }
        
        
        

""" Analyzes a list of QA dictionaries and returns a structured personality profile. """
async def analyze_personality(qa_data: list):
    
    try:
        # Convert list of dicts to a formatted string for the prompt
        qa_text = "\n".join([f"Q: {item['question']}\nA: {item['answer']}" for item in qa_data])

        prompt = f"""
Analyze the following questionnaire responses to determine the user's personality traits.

Data:
{qa_text}

Return ONLY valid JSON in the following format:
{{
  "your personality": "A descriptive analysis of the user's personality.",
  "how empathetic are you": {{
    "insight": "Detailed text analysis about empathy",
    "percentage": 85
  }},
  "How do you process experience": {{
    "insight": "Detailed text analysis about processing experiences",
    "percentage": 70
  }},
  "your idea level of closeness": {{
    "insight": "Detailed text analysis about relationship intimacy",
    "percentage": 90
  }},
  "How do you view the world?": {{
    "insight": "Detailed text analysis about their worldview",
    "percentage": 65
  }}
}}

Do not include markdown, explanations, or any text outside the JSON.
"""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=800
        )

        content = response.choices[0].message.content
        return json.loads(content)

    except Exception as e:
        print("Personality Analysis Error:", str(e))
        # Fallback in case of failure
        return {
            "your personality": "Balanced and thoughtful.",
            "how empathetic are you": "Moderate - 50%",
            "How do you process experience": "Logical - 50%",
            "your idea level of closeness": "Balanced - 50%",
            "How do you view the world?": "Realistic - 50%"
        }
        
        

async def transcribe_audio(
    audio_bytes: bytes,
    filename: str,
    language: Optional[str] = None
) -> str:
    """
    Transcribes a voice message into text using OpenAI's Whisper API.
 
    Args:
        audio_bytes: Raw bytes of the audio file.
        filename: Original filename (used so Whisper can infer the format).
        language: Optional ISO-639-1 hint (e.g. "hi", "en"). If None,
                  Whisper auto-detects the spoken language.
 
    Returns:
        The transcribed text.
 
    Raises:
        ValueError: If the file extension or size is invalid.
        RuntimeError: If the OpenAI client isn't configured, or the API call fails.
    """
    if not _whisper_client:
        raise RuntimeError("OpenAI credentials not configured on server")
 
    file_ext = (filename or "").split(".")[-1].lower()
    if file_ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise ValueError(
            f"Unsupported audio format. Allowed: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}"
        )
 
    if len(audio_bytes) == 0:
        raise ValueError("Uploaded audio file is empty")
 
    if len(audio_bytes) > MAX_AUDIO_FILE_SIZE_BYTES:
        raise ValueError("Audio file exceeds 25 MB limit")
 
    try:
        transcript = _whisper_client.audio.transcriptions.create(
            model="whisper-1",
            file=(filename, audio_bytes),
            language=language,
        )
    except Exception as e:
        raise RuntimeError(f"Transcription failed: {str(e)}")
 
    return transcript.text
 
