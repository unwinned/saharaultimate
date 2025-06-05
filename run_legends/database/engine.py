from database.engine import DbManager
from sqlalchemy import select, Boolean, func
from utils.client import Client
from utils.models import Proxy


class SaharaDbManager(DbManager):
    def __init__(self, db_path, base):
        super().__init__(db_path, base)

    async def create_base_note(self, pk, proxy):
        await super().create_base_note(pk, proxy)

    async def get_run_data(self):
        async with self.session.begin():
            result = await self.session.execute(select(self.base))
            users = result.scalars().all()
            return [{'client': Client(user.private_key), 'proxy': Proxy(user.proxy)}
                    for user in users]