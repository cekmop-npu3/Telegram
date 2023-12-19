import aiohttp

from typing import Union


class Database:
    __slots__ = '_base_url', '_params'

    def __init__(self, url: str, auth: str):
        self._base_url = url if url.endswith('/') else url + '/'
        self._params = {'auth': auth}

    async def get_data(self, path: str) -> Union[str, dict, None]:
        async with aiohttp.ClientSession() as session:
            async with session.get(url=f'{self._base_url}{path}' if path.endswith('.json') else f'{self._base_url}{path}.json', params=self._params) as response:
                return await response.json()

    async def update_data(self, path: str, data: dict) -> Union[str, dict, None]:
        async with aiohttp.ClientSession() as session:
            async with session.patch(url=f'{self._base_url}{path}' if path.endswith('.json') else f'{self._base_url}{path}.json', params=self._params, json=data) as response:
                return await response.json()

    async def delete_data(self, path: str) -> None:
        async with aiohttp.ClientSession() as session:
            async with session.delete(url=f'{self._base_url}{path}' if path.endswith('.json') else f'{self._base_url}{path}.json', params=self._params) as response:
                return await response.json()
