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

Analyze compatibility between these two users.

Evaluate:
- Lifestyle
- Career
- Core Values
- Adventure

Return ONLY JSON in this format:

{{
    "overallScore": 85,
    "summary": "short explanation here",
    "breakdown": [
        {{"category": "Lifestyle", "score": 90}},
        {{"category": "Career", "score": 75}},
        {{"category": "Core Values", "score": 95}},
        {{"category": "Adventure", "score": 60}}
    ]
}}
"""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=300
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