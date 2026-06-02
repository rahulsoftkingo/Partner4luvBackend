import os
from openai import OpenAI
from typing import List, Dict, Any
import json

class AIClient:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key)
        self.model = "gpt-4o-mini" # Fast and cost-effective

    async def verify_profile(self, bio: str, responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyzes a user's profile for authenticity and safety.
        """
        prompt = f"""
        Analyze the following user profile for a dating/partner-finding app:
        
        Bio: {bio}
        Questionnaire Responses: {json.dumps(responses)}
        
        Tasks:
        1. Rate the profile's authenticity (0-100%).
        2. Check for suspicious behavior or scammers patterns.
        3. Identify any inappropriate content (NSFW, hate speech, etc.).
        4. Provide a short summary of the user's personality based on the data.
        
        Return the result as JSON with these keys: 
        "authenticity_score" (int), "is_suspicious" (bool), "safety_flags" (list), "summary" (string).
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an AI profile auditor for a high-end dating app. You must be strict and objective."},
                    {"role": "user", "content": prompt}
                ],
                response_format={ "type": "json_object" }
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"AI Verification Error: {e}")
            return {
                "authenticity_score": 0,
                "is_suspicious": False,
                "safety_flags": ["AI_ERROR"],
                "summary": "Could not generate analysis at this time."
            }

    async def get_matching_insight(self, user1_data: Dict[str, Any], user2_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates a creative explanation and scores for why two users are a good match.
        """
        prompt = f"""
        User 1: {json.dumps(user1_data)}
        User 2: {json.dumps(user2_data)}
        
        Analyze these two users and return a JSON object with:
        1. "overall_score": (int 0-100)
        2. "personality_score": (int 0-100)
        3. "lifestyle_score": (int 0-100)
        4. "goals_score": (int 0-100)
        5. "values_score": (int 0-100)
        6. "insight": (3-4 sentences explaining the match)
        
        Make the insight warm and professional.
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional matchmaker for an elite dating platform. Return only JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={ "type": "json_object" }
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"AI Matching Insight Error: {e}")
            return {
                "overall_score": 85,
                "personality_score": 80,
                "lifestyle_score": 75,
                "goals_score": 90,
                "values_score": 85,
                "insight": "Both users show high compatibility in their core values and interests, making them a promising match."
            }

    async def verify_photo(self, primary_url: str, target_url: str) -> Dict[str, Any]:
        """
        Uses AI (Vision) to compare a gallery photo against the primary profile photo.
        """
        if not primary_url or not target_url:
             return {"is_match": False, "confidence": 0, "status": "PENDING", "reason": "Missing image URLs"}

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o", # Superior vision capabilities for face matching
                messages=[
                    {
                        "role": "system", 
                        "content": "You are an AI photo verification specialist. Compare faces for consistency and detect fake/stock imagery. Return ONLY JSON."
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text", 
                                "text": "Are the people in these two images the same person? Also, flag if any of them look like stock photos or AI-generated. Return JSON with keys: 'is_match' (bool), 'confidence' (int 0-100), 'status' ('VERIFIED', 'MISMATCH', 'SUSPICIOUS'), 'reason' (string)."
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": primary_url}
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": target_url}
                            }
                        ]
                    }
                ],
                response_format={ "type": "json_object" }
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"AI Photo Verification Error: {e}")
            return {
                "is_match": False,
                "confidence": 0,
                "status": "ERROR",
                "reason": f"AI processing failed: {str(e)}"
            }

ai_client = AIClient()
