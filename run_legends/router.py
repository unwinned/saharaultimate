from utils.router import MainRouter, DbRouter


class SaharaRouter(MainRouter, DbRouter):
    def get_choices(self):
        return ['faucet',
                'memebridge',
                'self-sender',
                'daily']

    def route(self, task, action):
        return dict(zip(self.get_choices(), [task.faucet,
                                             task.memebridge,
                                             task.self_sender,
                                             task.daily]))[action]

    @property
    def action(self):
        self.start_db_router()
        return self.get_action()
