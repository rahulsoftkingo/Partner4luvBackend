import socketio
from db import db
from datetime import datetime

# Initialize Socket.io with CORS allowed for all origins
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
socket_app = socketio.ASGIApp(sio)

@sio.event
async def connect(sid, environ):
    print(f"User connected: {sid}")

@sio.event
async def disconnect(sid):
    print(f"User disconnected: {sid}")

@sio.event
async def join_chat(sid, data):
    """
    User joins a specific conversation room (matchId).
    """
    match_id = data.get('matchId')
    if match_id:
        sio.enter_room(sid, f"match_{match_id}")
        print(f"SID {sid} joined match_{match_id}")

@sio.event
async def send_message(sid, data):
    """
    Real-time message sending.
    Data: {matchId, senderId, content, type}
    """
    match_id = data.get('matchId')
    sender_id = data.get('senderId')
    content = data.get('content')
    msg_type = data.get('type', 'TEXT')

    if not match_id or not sender_id:
        return

    # 1. Save to DB (using direct Prisma calls)
    try:
        # Find match to get conversationId
        match = await db.match.find_unique(
            where={"id": int(match_id)},
            include={"conversation": True}
        )
        
        if not match: return

        if not match.conversation:
            convo = await db.conversation.create(data={"matchId": int(match_id)})
            convo_id = convo.id
        else:
            convo_id = match.conversation.id

        # Create message
        message = await db.message.create(
            data={
                "conversationId": convo_id,
                "senderId": int(sender_id),
                "content": content,
                "type": msg_type
            }
        )

        # Update conversation timestamp
        await db.conversation.update(
            where={"id": convo_id},
            data={"updatedAt": datetime.now()}
        )

        # 2. Broadcast to room
        await sio.emit('new_message', {
            "matchId": match_id,
            "message": {
                "id": message.id,
                "senderId": sender_id,
                "content": content,
                "type": msg_type,
                "createdAt": message.createdAt.isoformat()
            }
        }, room=f"match_{match_id}")

    except Exception as e:
        print(f"SOCKET MESSAGE ERROR: {e}")

@sio.event
async def typing_status(sid, data):
    """
    Broadcast typing indicator to other users in the room.
    Data: {matchId, userId, isTyping}
    """
    match_id = data.get('matchId')
    user_id = data.get('userId')
    is_typing = data.get('isTyping')
    
    if match_id:
        await sio.emit('user_typing', {
            "userId": user_id,
            "isTyping": is_typing
        }, room=f"match_{match_id}", skip_sid=sid)
