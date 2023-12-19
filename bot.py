import asyncio
import aiohttp

from types_ import Message, User, States

from typing import TypedDict, Union


class Bot:
    def __init__(self, token: str):
        self.__token = token
        self._url = f'https://api.telegram.org/bot{token}'
        self.tasks = dict()
        self.messages = dict()
        self.commands = list()
        self.states = States(token, self.tasks, self.messages)

    async def _listener(self, ignore_tasks, timeout, offset: int = 0):
        async with aiohttp.ClientSession() as session:
            async with session.get(f'{self._url}/getUpdates?offset={offset}&timeout={timeout * bool(not ignore_tasks)}') as response:
                messages = (await response.json()).get('result')
                async with asyncio.TaskGroup() as tg:
                    for message in [Message(msg.get('message'), self.__token) for msg in messages]:
                        if not ignore_tasks:
                            tg.create_task(task[0](message, task[1])) if isinstance(task := self.tasks.get(message.content), list) else tg.create_task(task(message)) if message.content in self.tasks else [(tg.create_task(value[0](message, value[1])) if isinstance(value, list) else tg.create_task(value(message))) for value in self.messages.values()]
                    last_update_id = messages[-1].get('update_id') + 1 if messages else offset
                    await self._listener(False, timeout, last_update_id)

    async def get_me(self) -> User:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'{self._url}/getMe') as response:
                return User((await response.json()).get('result'), self.__token)

    async def set_name(self, name: str) -> bool:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'{self._url}/setMyName?name={name}') as response:
                return (await response.json()).get('result')

    async def set_description(self, description: str) -> bool:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'{self._url}/setMyDescription?description={description}') as response:
                return (await response.json()).get('result')

    async def _load_tasks(self, ignore_tasks, timeout):
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._listener(ignore_tasks, timeout))
            tg.create_task(self._load_commands())

    async def _load_commands(self) -> bool:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'{self._url}/setMyCommands', json={'commands': self.commands}) as response:
                return (await response.json()).get('result')

    def start_polling(self, *, ignore_tasks: bool, timeout: float = 100):
        try:
            asyncio.get_event_loop().run_until_complete(self._load_tasks(ignore_tasks, timeout))
        except KeyboardInterrupt:
            asyncio.get_event_loop().stop()

    def message_handler(self, *, command: TypedDict('command', {'command': str, 'description': str}) = None, text: Union[str, list[str]] = None, state: Union[str, list] = None):
        def inner(coro):
            if command:
                self.commands.append(command)
                self.tasks[f'/{command.get("command").lower()}'] = coro if state is None else [coro, state]
            elif text:
                if isinstance(text, str):
                    self.tasks[text] = coro if state is None else [coro, state]
                else:
                    for t in text:
                        self.tasks[t] = coro if state is None else [coro, state]
            else:
                self.messages[coro.__name__] = coro if state is None else [coro, state]
        return inner
