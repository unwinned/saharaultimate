import time
from utils.client import Client
from utils.utils import (retry, check_res_status, get_utc_now,
                         get_data_lines, sleep, Logger,
                         read_json, Contract, generate_random_hex_string,
                         get_utc_now)
from utils.models import RpcProviders, ChainExplorers, TxStatusResponse
from utils.galxe_utils.captcha import CapmonsterSolver
from utils.galxe_utils.task import GalxeTask
from .config import CONFIG
from .utils import pass_transaction
import random
from utils.galxe_utils.utils import MainGalxeTaskCompleter
from uuid import uuid4


class Task(Logger):
    def __init__(self, session, client: Client, db_manager):
        self.session = session
        self.client = client
        self.db_manager = db_manager
        super().__init__(self.client.address, additional={'pk': self.client.key,
                                                          'proxy': self.session.proxies.get('http')})
        self.explorer = 'https://testnet-explorer.saharalabs.ai/'
        self.captcha_solver = CapmonsterSolver(proxy=self.session.proxies.get('http'),
                                               api_key=CONFIG.SOLVERS.CAPSOLVER_API_KEY,
                                               logger=self.logger)
        self.galxe_task = GalxeTask(session=self.session,
                                    client=self.client,
                                    captcha_solver=self.captcha_solver)

    @property
    async def balance(self):
        return self.client.w3.from_wei(await self.client.w3.eth.get_balance(self.client.address), 'ether')


    async def sahara_login(self):
        challenge = (await self.get_challenge()).json()['challenge']
        jwt = (await self.login_request(challenge)).json()['accessToken']
        self.session.headers['Authorization'] = f'Bearer {jwt}'
        self.logger.success("Sahara login successful!")

    @retry()
    @check_res_status()
    async def get_challenge(self):
        url = 'https://legends.saharalabs.ai/api/v1/user/challenge'
        json_data = {
            'address': self.client.address,
            'timestamp': int(time.time() * 1000)
        }
        return await self.session.post(url, json=json_data)

    async def login_request(self, challenge):
        msg_to_sign = f'Sign in to Sahara!\nChallenge:{challenge}'
        url = 'https://legends.saharalabs.ai/api/v1/login/wallet'
        json_data = {
            'address': self.client.address,
            'sig': self.client.get_signed_code(msg_to_sign),
            'walletUUID': str(uuid4()),
            'walletName': 'Rabby Wallet',
            'timestamp': int(time.time() * 1000)
        }
        return await self.session.post(url, json=json_data)


    async def galxe_login(self):
        await self.galxe_task.galxe_login()
        if await self.galxe_task.is_address_registered():
            return
        else:
            await self.galxe_task.start_galxe_registration()

    async def faucet(self):
        self.client.define_new_provider(RpcProviders.ETH_MAINNET.value)
        balance = await self.balance
        if balance < 0.01:
            self.logger.error(f"You don't have enough ETH to faucet! Need 0.01, but you have {balance}")
            return
        while True:
            captcha = await self.captcha_solver.solve_turnstile(url='https://faucet.saharalabs.ai',
                                                                key="0x4AAAAAAA8hNPuIp1dAT_d9")
            captcha = captcha['token']
            self.session.headers.update({
                'origin': 'https://faucet.saharalabs.ai',
                'cf-turnstile-response': captcha,
                'sec-fetch-site': 'cross-site',
            })
            faucet_response = (await self.faucet_request()).json()
            if faucet_response.get('msg') == 'Request sent successfully. Please wait a moment.':
                self.logger.success("Successfully faucet!")
                return
            elif faucet_response.get("msg") == "Invalid captcha":
                self.logger.error("Invalid captcha! Trying again...")
            elif "You have exceeded the rate limit." in faucet_response.get("msg"):
                self.logger.info("Already faucet! Try again tomorrow!")
                return
            else:
                self.logger.error(f"Something went wrong - {faucet_response}. Trying again...")
                await sleep(*CONFIG.SETTINGS.SLEEP_BETWEEN_TASKS)

    @retry()
    @check_res_status(expected_statuses=[200, 201, 400, 429])
    async def faucet_request(self):
        url = 'https://faucet-api.saharaa.info/api/claim2'
        json_data = {
            'address': self.client.address
        }
        return await self.session.post(url, json=json_data)

    async def memebridge(self):
        balance = await self.balance
        if balance >= CONFIG.MEMEBRIDGE.MINIMUM_SAHARA:
            self.logger.info(f"Your SAHARA balance is {balance}. Skipping buying.")
            return
        self.client.define_new_provider(getattr(RpcProviders, CONFIG.MEMEBRIDGE.SOURCE_CHAIN.upper()).value)
        self.explorer = getattr(ChainExplorers, CONFIG.MEMEBRIDGE.SOURCE_CHAIN.upper()).value
        eth_balance = await self.balance
        random_value = round(random.uniform(*CONFIG.MEMEBRIDGE.BUY_AMOUNT), 6)
        if eth_balance < random_value:
            self.logger.info(f"You haven't enough {CONFIG.MEMEBRIDGE.SOURCE_CHAIN} ETH to buy. Your balance is {eth_balance} ETH.")
            return
        self.logger.info(f"Starting buying SAHARA for {random_value} ETH {CONFIG.MEMEBRIDGE.SOURCE_CHAIN}...")
        status, tx_hash = await self.mmb_tx(random_value)
        if status == TxStatusResponse.GOOD:
            return
        elif status == TxStatusResponse.INSUFFICIENT_BALANCE:
            self.logger.error(f"You haven't enough {CONFIG.MEMEBRIDGE.SOURCE_CHAIN} ETH to buy. Your balance is {eth_balance} ETH.")
            return

    @pass_transaction(success_message="Successfully bought testnet tokens!")
    async def mmb_tx(self, value):
        contract_address = self.client.w3.to_checksum_address("0x77A6ab7DC9096e7a311Eb9Bb4791494460F53c82")
        data = "0x11cd"
        transaction = {
            'chainId': await self.client.w3.eth.chain_id,
            'from': self.client.address,
            "to": contract_address,
            "value": self.client.w3.to_wei(value, "ether"),
            "data": data,
            'gasPrice': int(await self.client.w3.eth.gas_price * 1.1),
            'nonce': await self.client.w3.eth.get_transaction_count(self.client.address),
        }
        transaction['gas'] = await self.client.w3.eth.estimate_gas(transaction)
        signed_txn = self.client.w3.eth.account.sign_transaction(transaction, private_key=self.client.key)
        tx_hash = await self.client.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        return tx_hash.hex()

    async def daily(self):
        await self.galxe_login()
        await self.sahara_login()
        task_completer = MainGalxeTaskCompleter(client=self.client,
                                                session=self.session,
                                                token=None,
                                                logger=self.logger,
                                                captcha_solver=self.captcha_solver,
                                                db=None)
        campaign_id = 'GCNLYtpFM5'
        task_ids = [507361624877694976, 505649247018811392]
        self.logger.info("Starting completing galxe tasks...")
        for task_id in task_ids:
            await task_completer.complete_and_verify_task(cred_id=task_id, campaign_id=campaign_id)

        GOBI_DAILY_GALXE_TASK_IDS = ['1002', '1004']

        for task in GOBI_DAILY_GALXE_TASK_IDS:
            for _ in range(3):
                await self.flush_task(task)
                await sleep(3, 10)
                resp = await self.claim_task(task)
                if resp.status_code == 400:
                    if 'has been claimed' in resp.text:
                        self.logger.info("This task already claimed!")
                        break
                    self.logger.error(f"Error when claiming daily sahara task {resp.text}")
                else:
                    self.logger.success("Sahara daily task successfully completed!")
                    break
                await sleep(10, 30)

        balance = await self.balance
        if not balance:
            self.logger.error("You don't have any SAHARA balance!")
            return
        self.logger.info("Starting completing daily tx...")
        value = round(float(balance) * random.uniform(0.1, 0.9), 4)
        await self.self_transaction(value)
        await sleep(30, 60)
        for _ in range(3):
            await self.flush_task('1004')
            await sleep(3, 10)
            resp = await self.claim_task('1004')
            if resp.status_code == 400:
                if 'has been claimed' in resp.text:
                    self.logger.info("This task already claimed!")
                    break
                self.logger.error(f"Error when claiming daily sahara tx task {resp.text}")
            else:
                self.logger.success("Sahara daily tx task successfully completed!")
                break

    @retry()
    @check_res_status()
    async def flush_task(self, task_id):
        if type(task_id) is int:
            task_id = str(task_id)
        url = 'https://legends.saharalabs.ai/api/v1/task/flush'
        json = {
            'taskID': task_id,
            'timestamp': int(time.time() * 1000),
        }
        return await self.session.post(url, json=json)

    @retry()
    @check_res_status(expected_statuses=[200, 201, 400])
    async def claim_task(self, task_id):
        if type(task_id) is int:
            task_id = str(task_id)
        url = 'https://legends.saharalabs.ai/api/v1/task/claim'
        json = {
            'taskID': task_id,
            'timestamp': int(time.time() * 1000),
        }
        return await self.session.post(url, json=json)

    @pass_transaction(success_message="Daily tx successfully completed!")
    async def self_transaction(self, value):
        transaction = {
            'from': self.client.address,
            'to': self.client.address,
            'value': self.client.w3.to_wei(value, 'ether'),
            'gasPrice': int(await self.client.w3.eth.gas_price * 1.1),
            'nonce': await self.client.w3.eth.get_transaction_count(self.client.address),
            'chainId': await self.client.w3.eth.chain_id
        }
        transaction['gas'] = await self.client.w3.eth.estimate_gas(transaction)
        signed_txn = self.client.w3.eth.account.sign_transaction(transaction, private_key=self.client.key)
        tx_hash = await self.client.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        return tx_hash.hex()

    async def self_sender(self):
        pass