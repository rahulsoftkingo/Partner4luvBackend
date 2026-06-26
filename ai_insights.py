import os
import json
from dotenv import load_dotenv
from openai import OpenAI

# Load .env file
base_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

Also, suggest 5 relevant interest/lifestyle tags based on their input.

Return ONLY valid JSON in the following format:

{{
  "variations": {{
    "casual": "Text for casual bio variation...",
    "authentic": "Text for detailed/authentic bio variation...",
    "short": "Text for short/punchy bio variation..."
  }},
  "suggestedTags": ["Tag1", "Tag2", "Tag3", "Tag4", "Tag5"]
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