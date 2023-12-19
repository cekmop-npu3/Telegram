from __future__ import annotations

from datetime import datetime
import aiohttp
from json import dumps
from functools import wraps

from db import Database

from typing import TypedDict, Union


class PhotoSize:
    __slots__ = 'file_id', 'file_unique_id', 'width', 'height', 'file_size'

    def __init__(self, photo_data: dict):
        self.file_id: str = photo_data.get('file_id')
        self.file_unique_id: str = photo_data.get('file_unique_id')
        self.width: int = photo_data.get('width')
        self.height: int = photo_data.get('height')
        self.file_size: int = photo_data.get('file_size')


class UserProfilePhotos:
    __slots__ = 'total_count', 'photos'

    def __init__(self, photos_data: dict):
        self.total_count: int = photos_data.get('total_count')
        self.photos: list[PhotoSize] = [PhotoSize(photo_size[-1]) for photo_size in photos_data.get('photos')]

    def __contains__(self, item: Union[PhotoSize, str]):
        if isinstance(item, PhotoSize):
            return item in self.photos
        elif isinstance(item, str):
            return item in [photo.file_id for photo in self.photos]
        return False

    def __iter__(self):
        return Iterator(self.photos)

    def __getitem__(self, item):
        if item > len(self.photos):
            raise IndexError
        return self.photos[item]


class User:
    __slots__ = '__token', '_url', 'id', 'is_bot', 'first_name', 'last_name', 'username', 'language_code'

    def __init__(self, user_data: dict, token: str):
        self.__token = token
        self._url = f'https://api.telegram.org/bot{token}'
        self.id: int = user_data.get('id')
        self.is_bot: bool = user_data.get('is_bot')
        self.first_name: str = user_data.get('first_name')
        self.last_name: str = user_data.get('last_name')
        self.username: str = user_data.get('username')
        self.language_code: str = user_data.get('language_code', 'Eng')

    def __eq__(self, other):
        if isinstance(self, other) and other is not None:
            return all([self.id == other.id, self.is_bot == other.is_bot])
        return False

    async def get_photos(self, offset: int = 0, limit: int = 10) -> UserProfilePhotos:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'{self._url}/getUserProfilePhotos?user_id={self.id}&offset={offset}&limit={limit}') as response:
                return UserProfilePhotos((await response.json()).get('result'))


class KeyboardButton:
    __slots__ = '_text'

    def __init__(self, text: str):
        self._text = text

    def __str__(self):
        return self._text


class Iterator:
    __slots__ = '_iterable', '_counter'

    def __init__(self, iterable):
        self._iterable = iterable
        self._counter = 0

    def __next__(self):
        if self._counter > len(self._iterable):
            raise StopIteration
        value = self._iterable[self._counter]
        self._counter += 1
        return value


class ReplyKeyboardMarkup:
    __slots__ = '_buttons', '_keyboard'

    def __init__(self, resize_keyboard: bool = True, one_time_keyboard: bool = False):
        self._buttons = []
        self._keyboard = {'keyboard': self._buttons, 'resize_keyboard': resize_keyboard, 'one_time_keyboard': one_time_keyboard, 'selective': True}

    def __call__(self):
        return self._keyboard

    def row(self, buttons: list[KeyboardButton]):
        self._buttons.append(list(map(str, buttons)))
        return self

    def column(self, buttons: list[KeyboardButton]):
        [self._buttons.append([str(button)]) for button in buttons]
        return self


class Message:
    __slots__ = '__token', '_url', 'id', 'chat_id', 'content', 'user', 'unix_time', 'date', 'raw'

    def __init__(self, message_data: dict, token: str):
        self.__token = token
        self._url = f'https://api.telegram.org/bot{token}'
        self.id: int = message_data.get('message_id')
        self.chat_id: int = message_data.get('chat').get('id')
        self.content: str = message_data.get('text')
        self.user: User = User(message_data.get('from'), self.__token)
        self.unix_time: int = message_data.get('date')
        self.date: datetime = datetime.utcfromtimestamp(self.unix_time)
        self.raw = message_data

    def __eq__(self, other):
        if isinstance(self, other) and other is not None:
            return all([self.content == other.content, self.chat_id == other.chat_id, self.user == other.user])
        return False

    async def reply(self, *, text: str, parse_mode: str = '', reply_markup: ReplyKeyboardMarkup = '') -> TypedDict('ReplyMessage', {'message': Message, 'reply_to_message': Message}):
        async with aiohttp.ClientSession() as session:
            async with session.get(f'{self._url}/sendMessage?text={text}&chat_id={self.chat_id}&reply_to_message_id={self.id}&parse_mode={parse_mode}&reply_markup={dumps(reply_markup()) if reply_markup else dumps({"remove_keyboard": True})}') as response:
                reply = (await response.json()).get('result').get('reply_to_message')
                message = (await response.json()).get('result')
                del message['reply_to_message']
                return {'message': Message(message, self.__token), 'reply_to_message': Message(reply, self.__token)}

    async def send(self, *, text: str, parse_mode: str = '', reply_markup: ReplyKeyboardMarkup = '') -> Message:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'{self._url}/sendMessage?text={text}&chat_id={self.chat_id}&parse_mode={parse_mode}&reply_markup={dumps(reply_markup()) if reply_markup else dumps({"remove_keyboard": True})}') as response:
                return Message((await response.json()).get('result'), self.__token)


class States(Database):
    __slots__ = '__token', '_tasks', '_messages'

    def __init__(self, token: str, tasks: dict, messages: dict):
        super().__init__('url', 'token')
        self.__token = token
        self._tasks = tasks
        self._messages = messages

    def state_up(self, coro):
        @wraps(coro)
        async def wrapper(message: Message, state):
            if user := await self.get_data(f'users/{message.user.id}'):
                if user.get('state')[0] in state if isinstance(state, list) else user.get('state')[0] == state:
                    previous_state = user.get('previous_state')
                    if coro.__name__ != user.get('state')[0]:
                        if previous_state is None:
                            previous_state = [user.get('state')]
                        else:
                            previous_state.append(user.get('state'))
                    await self.update_data(
                        f'users/{message.user.id}',
                        {
                            'state': [coro.__name__, message.raw, message.content],
                            'previous_state': previous_state,
                        }
                    )
                    await self.update_data(f'users/{message.user.id}/updates', {coro.__name__: message.raw})
                    return await coro(message, {text: Message(msg, self.__token) for text, msg in (await self.get_data(f'users/{message.user.id}/updates')).items()})
        return wrapper

    def state_down(self, coro):
        @wraps(coro)
        async def wrapper(message: Message):
            if user := await self.get_data(f'users/{message.user.id}'):
                if (previous_state := user.get('previous_state')) is not None:
                    state = previous_state[-1]
                    answer = previous_state[-2] if len(previous_state) > 1 else []
                    previous_state.pop()
                    if answer:
                        previous_state.pop()
                        await self.update_data(
                            f'users/{message.user.id}',
                            {
                                'state': answer,
                                'previous_state': previous_state
                            }
                        )
                        await self._tasks.get(state[2])[0](Message(state[1], self.__token), answer[0]) if self._tasks.get(state[2]) is not None else await self._messages.get(state[0])[0](Message(state[1], self.__token), answer[0])
                    else:
                        await self.update_data(
                            f'users/{message.user.id}',
                            {
                                'state': state,
                            }
                        )
                        await self._tasks.get(state[2])(Message(state[1], self.__token))
                else:
                    return await coro(message)
        return wrapper

    def state_init(self, coro):
        @wraps(coro)
        async def wrapper(message: Message):
            await self.update_data(
                'users',
                {
                    message.user.id: {
                        'state': [coro.__name__, message.raw, message.content],
                        'previous_state': []
                    }
                }
            )
            return await coro(message)
        return wrapper
