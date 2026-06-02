import os
import json
from openai import OpenAI
from typing import List, Dict
from dotenv import load_dotenv
# Load environment variables from parent directory's .env
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(base_dir, '.env')
load_dotenv(dotenv_path)

api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key) if api_key else None

async def generate_option_tags(question_text: str, options: List[str]) -> List[List[str]]:
    """
    Uses AI to generate semantic matching tags for each option of a question.
    Returns a list of tag-lists (one for each option).
    """
    if not client:
        print("OpenAI Client not initialized (missing API key). Falling back to keyword tagging.")
        return [keyword_tagger(opt) for opt in options]
    prompt = f"""
    You are an AI matching expert for a premium dating app. 
    Analyze the following question and its options. 
    For each option, provide 3-5 concise semantic tags (snake_case) that represent the user's personality, lifestyle, or preferences based on that choice.
    
    Question: {question_text}
    Options: {', '.join(options)}
    
    Return ONLY a JSON array of arrays, where each inner array contains the tags for the corresponding option.
    Example: [["introvert", "homebody"], ["adventurous", "traveler"]]
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "You are a professional psychologist and matching expert."},
                      {"role": "user", "content": prompt}],
            response_format={ "type": "json_object" }
        )
        
        result = json.loads(response.choices[0].message.content)
        if isinstance(result, dict):
            for key in result:
                if isinstance(result[key], list):
                    return result[key]
        return result
    except Exception as e:
        print(f"AI Tagging Error: {e}. Falling back to keyword tagging.")
        return [keyword_tagger(opt) for opt in options]

def keyword_tagger(text: str) -> List[str]:
    """Simple keyword-based fallback tagger."""
    text = text.lower()
    tags = []
    mapping = {
        "travel": ["adventurous", "explorer"],
        "sport": ["active", "fitness"],
        "daily": ["consistent", "routine"],
        "friend": ["social", "extrovert"],
        "family": ["family_oriented"],
        "alone": ["introvert", "independent"],
        "peace": ["peaceful", "calm"],
        "fun": ["fun_loving", "humorous"],
        "trust": ["loyal", "deep_connector"],
        "emotional": ["sensitive", "empathetic"],
        "security": ["stability_seeker"],
        "sex": ["intimate", "physical_touch"],
        "success": ["ambitious", "career_oriented"],
        "art": ["creative", "cultured"],
        "book": ["intellectual", "learner"],
        "home": ["homebody"],
        "party": ["social_butterfly"],
        "active": ["high_energy"],
        "planning": ["organized", "structured"]
    }
    for key, val in mapping.items():
        if key in text:
            tags.extend(val)
    return list(set(tags)) or ["balanced"]

async def update_question_tags(db, question_id: int):
    """
    Fetches a question and its options, generates tags, and updates the DB.
    """
    question = await db.question.find_unique(
        where={"id": question_id},
        include={"options": True}
    )
    if not question or not question.options:
        return

    option_texts = [opt.text for opt in question.options]
    all_tags = await generate_option_tags(question.text, option_texts)
    
    for i, opt in enumerate(question.options):
        tags = all_tags[i] if i < len(all_tags) else []
        await db.questionoption.update(
            where={"id": opt.id},
            data={"tags": tags}
        )
    print(f"Successfully updated AI tags for question: {question_id}")
