from flask import request, current_app, session
from flask_socketio import emit, join_room, leave_room
from pwnedapi.models import Config, User, Message, Room
from pwnedapi import socketio, db
from werkzeug.exceptions import Forbidden
import jwt
import traceback

def parse_jwt():
    request.jwt = {}
    token = request.cookies.get('access_token')
    if Config.get_value('BEARER_AUTH_ENABLE'):
        token = request.args.get('access_token')
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
    except:
        return
    request.jwt = payload

def load_user():
    # g doesn't persist across events, so session is used to track the authenticated user
    # since websockets don't use session, using it should be transparent to the client
    # for some reason session.user does not equate to <object>.user, so the id property
    # must be used to make equality comparisons
    session.user = None
    uid = request.jwt.get('sub')
    if uid:
        session.user = User.query.get(uid)

@socketio.on('connect')
def connect_handler():
    parse_jwt()
    load_user()
    if not session.user:
        return False
    emit('log', f"Socket connected.")
    # preload users
    users = [u.serialize() for u in User.query.all()]
    emit('loadUsers', {'users': users})
    # join membered rooms
    rooms = [r.serialize_with_context(session.user) for r in session.user.rooms]
    for room in rooms:
        join_room(room['name'])
        emit('log', f"Joined room: id={room['id']}, name={room['name']}")
    # preload rooms
    emit('loadRooms', {'rooms': rooms})
    # load the default room
    emit('loadRoom', rooms[0])

@socketio.on('create-room')
def create_room_handler(data):
    # needed to re-establish session.user after commit
    current_user_id = session.user.id
    room = Room.get_by_name(data['name'])
    if not room:
        # create the room
        room = Room(
            name=data['name'],
            private=data['private'],
        )
        db.session.add(room)
        db.session.commit()
        # initialize memberships
        for member in data['members']:
            user = User.query.get(member)
            user.create_membership(room)
        # TODO: if private, emit socket message for all users to update rooms
        emit('log', f"Created room: id={room.id}, name={room.name}")
        # join created room
        join_room(room.name)
        emit('log', f"Joined room: id={room.id}, name={room.name}")
        # reload rooms
        session.user = User.query.get(current_user_id)
        rooms = [r.serialize_with_context(session.user) for r in session.user.rooms]
        emit('loadRooms', {'rooms': rooms})
    # load the room
    emit('loadRoom', room.serialize_with_context(session.user))

#unused
@socketio.on('join-room')
def join_room_handler(data):
    join_room(data['name'])
    emit('log', f"Joined room: id={data['id']}, name={data['name']}")

# unused
@socketio.on('leave-room')
def leave_room_handler(data):
    leave_room(data['name'])
    emit('log', f"Left room: {data['id']}")

@socketio.on('create-message')
def create_message_handler(data):
    message = Message(
        comment=data['message']['comment'],
        author=session.user,
        room_id=data['room']['id']
    )
    db.session.add(message)
    db.session.commit()
    emit('newMessage', message.serialize(), room=data['room']['name'])

@socketio.on('delete-message')
def delete_message_handler(data):
    message = Message.query.get(data['message']['id'])
    if message.author.id != session.user.id and session.user.is_admin == False:
        raise Forbidden('Unauthorized deletion attempt.')
    # create response object before deleting it
    serialized_message = message.serialize()
    db.session.delete(message)
    db.session.commit()
    emit('delMessage', serialized_message, room=data['room']['name'])

@socketio.on_error_default
def default_error_handler(e):
    emit('log', request.event)
    print(traceback.format_exc())
