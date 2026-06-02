import asyncio
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from prisma import Prisma
from prisma.enums import QuestionType

async def main():
    prisma = Prisma()
    await prisma.connect()

    print("Cleaning up existing questionnaire data...")
    await prisma.userresponse.delete_many()
    await prisma.questionoption.delete_many()
    await prisma.question.delete_many()
    await prisma.questionnairecategory.delete_many()

    # 1. Define Phases (Categories)
    phases = [
        {"id": 0, "name": "basic", "title": "Basic Information", "description": "Now it's about your day-to-day life. Habits, opinions, quirks..."},
        {"id": 1, "name": "personality", "title": "Personality Test", "description": "Let's dive deeper into how you spend your time and what makes you, you."},
        {"id": 2, "name": "psychology", "title": "Situational Psychology", "description": "Now it's about what's important to you in love and how you react in different situations."},
        {"id": 3, "name": "lifestyle", "title": "Day-To-Day life", "description": "Now it's about your day-to-day life. Habits, opinions, quirks..."},
    ]

    print("Seeding Categories...")
    category_map = {}
    for p in phases:
        cat = await prisma.questionnairecategory.create(
            data={
                "name": p["name"],
                "title": p["title"],
                "description": p["description"],
                "order": p["id"]
            }
        )
        category_map[p["id"]] = cat.id

    # 2. Define Questions
    # Mapping JS types to Prisma QuestionType
    # single -> SINGLE_CHOICE, multi -> MULTIPLE_CHOICE
    questions = [
        # Phase 0
        {"phase": 0, "text": "Which statement best describes your ideal partner?", "type": "SINGLE_CHOICE", "options": ["We have overlapping interests.", "There is a strong attraction between us.", "We find practical solutions for problems together.", "We are very close and understand each other.", "We have a positive, optimistic outlook.", "We enjoy shared activities."]},
        {"phase": 0, "text": "How easily do you get excited about new things?", "type": "SINGLE_CHOICE", "options": ["Easily, because I love new experiences.", "Easily, because typically something good comes out of it.", "It depends - I'd have to understand what's involved first.", "I don't get that excited by new things.", "Not usually; I'm pretty skeptical."]},
        {"phase": 0, "text": "Is it easy for you to trust people?", "type": "SINGLE_CHOICE", "options": ["Yes, mostly", "I try", "Not really, I'm more cautious", "Depends on the context"]},
        {"phase": 0, "text": "Other than love, why are you interested in a relationship?", "type": "MULTIPLE_CHOICE", "options": ["Everyday life is easier together.", "Emotional security.", "Someone I can trust completely.", "Regular sex.", "Spend free time together.", "Don't want to be alone", "More security in every way"]},
        
        # Phase 1
        {"phase": 1, "text": "You're alone at a party. What do you do?", "type": "SINGLE_CHOICE", "options": ["I would actively approach others, so I could meet new people.", "I would be open to conversations but would not actively approach others.", "I would feel uncomfortable and prefer to leave.", "I'd make the most of it."]},
        {"phase": 1, "text": "What would the people who know you well say about you?", "type": "MULTIPLE_CHOICE", "options": ["Open to new opportunities", "Helpful; always looking for others", "Determined and optimized", "Thoughtful and reserved", "Enjoys peace and relaxation", "Enjoys quality time alone", "Social and likes to spend time with others"]},
        {"phase": 1, "text": "Which values are most important to you?", "type": "MULTIPLE_CHOICE", "options": ["Friendship/Relationship", "Love & Partnership", "Success and career", "Peace & harmony relaxation", "Freedom and independence", "Discovering new things and adventuring", "Security & stability", "Helpfulness & Social Commitment"]},
        {"phase": 1, "text": "Do you feel more at ease within your own four walls than when you are out and about in the company of people?", "type": "SINGLE_CHOICE", "options": ["Yes", "No"]},
        {"phase": 1, "text": "Do you sleep with the window open?", "type": "SINGLE_CHOICE", "options": ["Yes, definitely", "Yes, if possible", "I'd be okay either way.", "No, not really.", "No, absolutely not"]},
        {"phase": 1, "text": "You're out and about, and you meet an attractive person. What would you do?", "type": "SINGLE_CHOICE", "options": ["I'd go over and talk to them.", "I'd smile at them and see if they smile back before starting a conversation.", "I wouldn't dare to talk to them.", "I'd wait and see if something happens."]},
        {"phase": 1, "text": "Some people are most active in the mornings, others are more so in the evenings. How about you?", "type": "SINGLE_CHOICE", "options": ["Morning person", "Evening person", "In my case there is no difference"]},
        {"phase": 1, "text": "How do you approach planning a date?", "type": "MULTIPLE_CHOICE", "options": ["I like to plan what we're going to do", "I'll propose an idea, but I'm ok doing what my date wants to do if they have something in mind.", "I start by thinking about what we both like.", "I'm unsure and prefer to leave the planning to my date.", "I prefer a quiet and relaxed date in a place without a lot of hustle and bustle.", "Thoughtful and reserved", "I prefer dates where we can experience a lot."]},
        {"phase": 1, "text": "How do you prefer to dress?", "type": "SINGLE_CHOICE", "options": ["Comfortable and functional", "Eye-Catching", "Situationally appropriate", "Subtle and reserved", "Elegant"]},

        # Phase 2
        {"phase": 2, "text": "You're on a date with someone who tells you about their bad day. How would you react?", "type": "SINGLE_CHOICE", "options": ["I listen attentively and try to understand the person.", "I listen, but try to change the topic to something else.", "I would feel uncomfortable and not know how to react.", "I'd tell something funny to cheer up the other person."]},
        {"phase": 2, "text": "Sometimes people hurt you. How do you react?", "type": "SINGLE_CHOICE", "options": ["I try to overlook it.", "I'll think they didn't mean it that way and move on.", "I'm sure i'll find a way to deal with it.", "It will be on my mind for some time.", "I'll tell them I'm upset and express my point of view clearly.", "Even if I were hurt, I would want to understand why they acted that way before I react myself."]},
        {"phase": 2, "text": "Imagine you're at a party with your partner and you notice that they're flirting with someone else. How would you react?", "type": "SINGLE_CHOICE", "options": ["I flirt as well.", "I find a way to make it clear I'm their partner.", "I'm frustrated, but ignore it.", "I don't feel comfortable intervening.", "I'll be cold and distant with my partner.", "No big deal, a little fun is allowed."]},
        {"phase": 2, "text": "Imagine you're meeting your date for the first time. How do you act?", "type": "SINGLE_CHOICE", "options": ["I'm reserved and prefer if the other person takes the lead in the conversation.", "I wait and see how the conversation is going before revealing too much about myself.", "You're talkative, open, and like to take the lead in the conversation.", "You listen attentively and tailor the conversation to your date's vibe."]},
        {"phase": 2, "text": "You're on a date and someone at the next table is talking loudly on their phone. How do you react?", "type": "SINGLE_CHOICE", "options": ["I find us a quieter place.", "I ask the person to quiet down or take their call elsewhere.", "I try to ignore it and focus on my date.", "I overlook it, everyone has an important call sometimes.", "I just talk louder myself.", "I try to figure out if it bothers my date and then react accordingly."]},
        {"phase": 2, "text": "Which arrangement intuitively appeals to you the most?", "type": "SINGLE_CHOICE", "options": ["Structured Grid Arrangement", "Circular Harmony Arrangement"]},
        {"phase": 2, "text": "Which image do you find more attractive?", "type": "SINGLE_CHOICE", "options": ["Geometric Circular Design", "Modern Abstract Shape"]},
        {"phase": 2, "text": "When you have a topic that is very important to you, do you feel the need to share it with your partner?", "type": "SINGLE_CHOICE", "options": ["Yes, it's very important to me to share as much as possible.", "Yes, so we better understand how we think and feel.", "I spend time reflecting about it on my own first.", "Not really, I'm not into discussions.", "Sometimes - it depends if the topic makes sense for us to discuss."]},
        {"phase": 2, "text": "You have plans to go to an event with a good friend. They cancel last minute. How do you react?", "type": "SINGLE_CHOICE", "options": ["I'm sad and I struggle to get over it.", "I ask why they can't make it to find out if they're ok.", "It's not a problem for me, sometimes things come up.", "I'm disappointed because I wouldn't attend the event alone.", "I try to convince them to come."]},

        # Phase 3
        {"phase": 3, "text": "Do you smoke", "type": "SINGLE_CHOICE", "options": ["Yes", "From time to time", "NO"]},
        {"phase": 3, "text": "How important is loyalty in a relationship to you?", "type": "SINGLE_CHOICE", "options": ["Loyalty is the most important thing to me to build trust and open up emotionally.", "It is very important to me that we develop a shared understanding of loyalty and talk about it.", "Important, but there are also other important aspects in a relationship.", "Important, but I could forgive under certain circumstances.", "Important, though each person needs freedom for their own activities and friends as well.", "Not that important, as long as the relationship is stable overall.", "Not that important, I find openness and flexibility in relationships more important."]},
        {"phase": 3, "text": "If someone contradicts you when you know that you are right, how do you usually react?", "type": "SINGLE_CHOICE", "options": ["I get annoyed about their know-it-all attitude, but don't say anything.", "It doesn't matter, being right isn't important to me.", "I try to convince the other person.", "I try to understand why the other person said that.", "I make it clear that I'm right and explain why."]},
        {"phase": 3, "text": "Which of these three plants do you enjoy looking at the most?", "type": "VISUAL_IMAGE", "options": ["Mountain View", "Lush Bush", "Sunset View"]},
        {"phase": 3, "text": "When you have a conflict with your partner, how do you react?", "type": "SINGLE_CHOICE", "options": ["I'd rather not fight, so I'll adapt as needed.", "I stand by my convictions and advocate for them, even if it gets difficult.", "I tend to withdraw rather than talk about it.", "I'm not upset, and I know we'll find a way to problem-solve together.", "I try to better understand their feelings and perspectives.", "I try to find a compromise and will find an outlet elsewhere if needed."]},
        {"phase": 3, "text": "Do you drink alcohol?", "type": "SINGLE_CHOICE", "options": ["Yes, at mealtimes, socially or to relax", "From time to time.", "Not at all."]},
        {"phase": 3, "text": "How important is sexuality to you?", "type": "SINGLE_CHOICE", "options": ["Very Important", "Important", "Not particularly important", "Not important."]},
        {"phase": 3, "text": "When you plan something, how do you go about it?", "type": "SINGLE_CHOICE", "options": ["I know exactly what I want and plan it that way.", "I plan the essentials, but don't need to spell out every detail.", "I put a lot of thought into it because I can get stressed by the unexpected.", "I want to do something new and exciting.", "I bring the enthusiasm - it's going to be fun regardless."]},
    ]

    print("\nSeeding Questions and Options...")
    for idx, q in enumerate(questions):
        question = await prisma.question.create(
            data={
                "categoryId": category_map[q["phase"]],
                "text": q["text"],
                "type": q["type"],
                "order": idx
            }
        )
        
        # Create Options with weights (default 10 for simplicity)
        for opt_text in q["options"]:
            await prisma.questionoption.create(
                data={
                    "questionId": question.id,
                    "text": opt_text,
                    "value": 10
                }
            )
        print(f"Created Question {idx+1}")

    await prisma.disconnect()
    print("\nQuestionnaire seed completed!")

if __name__ == "__main__":
    asyncio.run(main())
