import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_onboarding():
    print("Testing Onboarding Questions...")
    resp = requests.get(f"{BASE_URL}/auth/user/onboarding/questions")
    if resp.status_code == 200:
        print("SUCCESS: Questions fetched successfully")
        data = resp.json()
        print(f"Total categories: {len(data['categories'])}")
    else:
        print(f"❌ Failed to fetch questions: {resp.status_code}")

def test_profile_setup():
    print("\nTesting Profile Setup...")
    payload = {
        "userId": 1,
        "bio": "Test bio",
        "gender": "MALE",
        "city": "Test City"
    }
    resp = requests.post(f"{BASE_URL}/auth/user/profile/setup", json=payload)
    if resp.status_code == 200:
        print("SUCCESS: Profile setup successful")
    else:
        print(f"FAILED: Profile setup failed: {resp.text}")

if __name__ == "__main__":
    try:
        test_onboarding()
        test_profile_setup()
    except Exception as e:
        print(f"Error connecting to server: {e}. Is the backend running?")
