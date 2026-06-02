import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env in the backend directory
base_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(base_dir, '.env')
load_dotenv(dotenv_path)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_match_insight(user1_data: dict, user2_data: dict):
    """
    Generates a structured personality insight between two users.
    Data should include tags, occupation, and bio.
    """
    import json
    try:
        u1_tags = user1_data.get("tags", [])
        u2_tags = user2_data.get("tags", [])
        u1_bio = user1_data.get("bio", "")
        u2_bio = user2_data.get("bio", "")
        
        prompt = f"""
        User 1 Details:
        - Bio: {u1_bio}
        - Personality Tags: {", ".join(u1_tags)}
        
        User 2 Details:
        - Bio: {u2_bio}
        - Personality Tags: {", ".join(u2_tags)}
        
        Analyze the compatibility of these two users across 4 categories: Lifestyle, Career, Core Values, and Adventure.
        Provide an overall compatibility score (0-100) and a score for each category.
        Also provide a short 2-3 sentence summary explanation.
        
        Return ONLY a JSON object in this exact format:
        {{
            "overallScore": 85,
            "summary": "...",
            "breakdown": [
                {{ "category": "Lifestyle", "score": 90 }},
                {{ "category": "Career", "score": 75 }},
                {{ "category": "Core Values", "score": 95 }},
                {{ "category": "Adventure", "score": 60 }}
            ]
        }}
        """

        response = client.chat.completions.create(
            model="gpt-4o-2024-05-13", # Using latest model for structured output
            messages=[{"role": "user", "content": prompt}],
            response_format={ "type": "json_object" },
            max_tokens=300
        )
        
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"AI Insight Error: {str(e)}")
        # Reliable Fallback
        return {
            "overallScore": 75,
            "summary": "You both share a balanced approach to life, blending personal interests with professional goals effectively.",
            "breakdown": [
                { "category": "Lifestyle", "score": 70 },
                { "category": "Career", "score": 75 },
                { "category": "Core Values", "score": 80 },
                { "category": "Adventure", "score": 75 }
            ]
        }

def calculate_match_score(user1_tags: list, user2_tags: list):
    # Keep as fallback helper
    if not user1_tags or not user2_tags: return 50
    s1, s2 = set(user1_tags), set(user2_tags)
    intersection = len(s1.intersection(s2))
    union = len(s1.union(s2))
    return round((intersection / union) * 100) if union > 0 else 50
