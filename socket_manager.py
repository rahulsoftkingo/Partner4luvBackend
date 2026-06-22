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
    match_id = data.get('matchId')
    sender_id = data.get('senderId')
    content = data.get('content')
    msg_type = data.get('type', 'TEXT')
    duration = data.get('duration')  # only relevant for AUDIO/VIDEO

    if not match_id or not sender_id:
        return

    if msg_type == 'AUDIO' and not content:
        return  # audio URL missing, invalid message

    try:
        match = await db.match.find_unique(
            where={"id": int(match_id)},
            include={"conversation": True}
        )
        if not match:
            return

        # security check: sender match ka participant hai ya nahi
        if int(sender_id) not in (match.user1Id, match.user2Id):
            print(f"Unauthorized sender {sender_id} for match {match_id}")
            return

        if not match.conversation:
            convo = await db.conversation.create(data={"matchId": int(match_id)})
            convo_id = convo.id
        else:
            convo_id = match.conversation.id

        message = await db.message.create(
            data={
                "conversationId": convo_id,
                "senderId": int(sender_id),
                "content": content,
                "type": msg_type,
                **({"duration": duration} if duration is not None else {})
            }
        )

        await db.conversation.update(
            where={"id": convo_id},
            data={"updatedAt": datetime.now()}
        )

        await sio.emit('new_message', {
            "matchId": match_id,
            "message": {
                "id": message.id,
                "senderId": sender_id,
                "content": content,
                "type": msg_type,
                "duration": duration,
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
