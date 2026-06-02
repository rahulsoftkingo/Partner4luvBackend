import asyncio
import sys
import os
from dotenv import load_dotenv
load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prisma import Prisma
from utils.ai_tagger import update_question_tags

async def main():
    db = Prisma()
    await db.connect()

    print("Cleaning existing questionnaire data...")
    try:
        await db.userresponse.delete_many()
        await db.questionoption.delete_many()
        await db.question.delete_many()
        await db.questionnairecategory.delete_many()
    except Exception as e:
        print(f"Cleanup error (ignoring): {e}")

    categories_data = [
        {
            "name": "intent",
            "title": "Relationship Intent",
            "description": "What are you looking for in a partner? Your goals and expectations.",
            "imageUrl": "https://images.unsplash.com/photo-1511632765486-a01980e01a18?q=80&w=1000"
        },
        {
            "name": "personality",
            "title": "Personality Test",
            "description": "Your traits, social habits, and how you view yourself.",
            "imageUrl": "https://images.unsplash.com/photo-1506126613408-eca07ce68773?q=80&w=1000"
        },
        {
            "name": "situational",
            "title": "Situational Psychology",
            "description": "How do you react in different life scenarios? Understanding your behavior.",
            "imageUrl": "https://images.unsplash.com/photo-1516062423079-7ca13cdc7f5a?q=80&w=1000"
        },
        {
            "name": "lifestyle",
            "title": "Day-To-Day Life",
            "description": "Your habits, opinions, and quirks. It's worth being honest - after all, you don't want to pretend to be someone you're not.",
            "imageUrl": "https://images.unsplash.com/photo-1517486808906-6ca8b3f04846?q=80&w=1000"
        }
    ]

    cat_map = {}
    for c in categories_data:
        cat = await db.questionnairecategory.create(data=c)
        cat_map[c['name']] = cat.id
        print(f"Created category: {c['title']}")

    # --- QUESTIONS DATA ---
    questions_data = {
        "intent": [
            {
                "text": "Which statement best describes your ideal partner?",
                "type": "SINGLE_CHOICE",
                "options": ["We have overlapping interests.", "There is a strong attraction between us.", "We find practical solutions for problems together.", "We are very close and understand each other without even having to explain.", "We have a positive, optimistic outlook on our life.", "We enjoy shared activities."]
            },
            {
                "text": "Other than love, why are you interested in a relationship?",
                "type": "MULTIPLE_CHOICE",
                "options": ["Everyday life is easier when you are a couple rather than going at it alone.", "I want the emotional security of having someone by my side.", "I'd like to have someone I can trust completely.", "I'd like to have regular sex.", "I simply don't want to be alone", "A relationship offers more security in every way", "Everything is more fun in a relationship"]
            }
        ],
        "personality": [
            {
                "text": "What would the people who know you well say about you?",
                "type": "MULTIPLE_CHOICE",
                "options": ["Helpful; always looking for others", "Determined and optimized", "Thoughtful and reserved", "Social and likes to spend time with others", "Fun & humor"]
            },
            {
                "text": "You're alone at a party. What do you do?",
                "type": "SINGLE_CHOICE",
                "options": ["I would actively approach others, so I could meet new people.", "I would be open to conversations but would not actively approach others.", "I would feel uncomfortable and prefer to leave.", "I'd make the most of it."]
            },
            {
                "text": "Which values are most important to you?",
                "type": "MULTIPLE_CHOICE",
                "options": ["Friendship/Relationship", "Love & Partnership", "Success and career", "Peace & harmony relaxation", "Freedom and independence", "Security & stability", "Helpfulness & Social Commitment"]
            }
        ],
        "situational": [
            {
                "text": "You're on a date with someone who tells you about their bad day. How would you react?",
                "type": "SINGLE_CHOICE",
                "options": ["I listen attentively and try to understand the person.", "I listen, but try to change the topic to something else.", "I'd tell something funny to cheer up the other person.", "I try to figure out if it bothers my date and then react accordingly."]
            },
            {
                "text": "Imagine you're at a party with your partner and you notice that they're flirting with someone else. How would you react?",
                "type": "SINGLE_CHOICE",
                "options": ["I flirt as well.", "I find a way to make it clear I'm their partner.", "I would feel uncomfortable and not know how to react.", "I'll tell them I'm upset and express my point of view clearly.", "No big deal, a little fun is allowed."]
            }
        ],
        "lifestyle": [
            {
                "text": "How regularly do you play sports?",
                "type": "SINGLE_CHOICE",
                "options": ["Daily", "Several times a week", "Several times a month", "Less often"]
            },
            {
                "text": "How do you like to spend your free time?",
                "type": "SINGLE_CHOICE",
                "options": ["With friends or family in a social setting", "Relaxing at home", "Being active", "With a cultural or other activity", "Taking some solo time for myself", "I'd like to spend my free time with someone."]
            }
        ]
    }

    for cat_name, qs in questions_data.items():
        cat_id = cat_map.get(cat_name)
        if not cat_id: continue
        
        for q_data in qs:
            question = await db.question.create(data={
                "text": q_data["text"],
                "type": q_data["type"],
                "categoryId": cat_id,
                "isRequired": True
            })
            for i, opt_text in enumerate(q_data["options"]):
                await db.questionoption.create(data={
                    "text": opt_text,
                    "questionId": question.id,
                    "value": (i + 1) * 10 # Mock value for scoring
                })
            
            # Generate AI tags for the question
            await update_question_tags(db, question.id)
            print(f"Created question in {cat_name}: {q_data['text'][:30]}...")

    await db.disconnect()
    print("\nSeeding completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
