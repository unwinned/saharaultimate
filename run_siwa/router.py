from utils.router import MainRouter, DbRouter


class SiwaRouter(MainRouter, DbRouter):
    def get_choices(self):
        return ['faucet',
                'memebridge',
                'daily']

    def route(self, task, action):
        return dict(zip(self.get_choices(), [task.faucet,
                                             task.memebridge,
                                             task.daily]))[action]

    @property
    def action(self):
        self.start_db_router()
        return self.get_action()
