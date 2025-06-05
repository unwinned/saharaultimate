import time
from utils.client import Client
from utils.utils import (retry, check_res_status, get_utc_now,
                         get_data_lines, sleep, Logger,
                         read_json, Contract, generate_random_hex_string,
                         get_utc_now)
from utils.models import RpcProviders, ChainExplorers, TxStatusResponse
from utils.galxe_utils.captcha import CapmonsterSolver
from utils.galxe_utils.task import GalxeTask
from run_legends.config import CONFIG
from run_legends.utils import pass_transaction
from datetime import datetime
import pytz
import random
import json
import string
import openai
from io import BytesIO
import os
from .paths import languages, countries, names, lastnames, prompts
from eth_keys import keys
from utils.galxe_utils.utils import MainGalxeTaskCompleter
from uuid import uuid4


class Task(Logger):
    def __init__(self, session, client: Client, db_manager):
        self.session = session
        self.client = client
        self.db_manager = db_manager
        super().__init__(self.client.address, additional={'pk': self.client.key,
                                                          'proxy': self.session.proxies.get('http')})
        self.explorer = 'https://testnet-explorer.saharalabs.ai/tx/'
        self.captcha_solver = CapmonsterSolver(proxy=self.session.proxies.get('http'),
                                               api_key=CONFIG.SOLVERS.CAPSOLVER_API_KEY,
                                               logger=self.logger)
        self.galxe_task = GalxeTask(session=self.session,
                                    client=self.client,
                                    captcha_solver=self.captcha_solver)


    @property
    async def balance(self):
        return self.client.w3.from_wei(await self.client.w3.eth.get_balance(self.client.address), 'ether')
        
        
    async def daily(self):
        await self.login_request()
        check = await self.check_if_reg_account()
        
        if check == True:
            self.logger.info("Start registering account....")
            await self.register_profile(await self.login_request())
        else:
            self.logger.info("You already have account here, skipping registration")
    
        await self.chat_gpt_request()
        await self.create_dataset()
        return
            
        
    async def check_if_reg_account(self):
        url = "https://login.saharalabs.ai/api/users/v3/profile"
        jwt = await self.login_request()
        headers = {'Authorization': f'Bearer {jwt}'}
        response = await self.session.get(url=url, headers=headers)
        data = response.json()
        
        if data['data']['firstName'] == "" and data['data']['lastName'] == "":
            return True
        else:
            return False
        
        
    async def check_need_data(self):
        jwt = await self.login_request()
        check = await self.check_if_reg_account()
        if check == False:
            url = "https://login.saharalabs.ai/api/users/v3/profile"
            headers = {'Authorization': f'Bearer {jwt}'}
            response = await self.session.get(url=url, headers=headers)
            data = response.json()
            language = data['data']['languages'][0]
            return language
            
        
    async def generate_message_request(self):
        url = "https://login.saharalabs.ai/v1/auth/generate-message"
        
        json_data = {
            'address': self.client.address,
            'chainId': 313313
        }
        
        response = await self.session.post(url, json=json_data)
        
        if response.status_code == 200:
            data = response.json()

        return data['data']['message']


    async def login_request(self):
        msg_to_sign = await self.generate_message_request()
    
        private_key = self.client.key
        private_key_bytes = bytes.fromhex(private_key[2:] if private_key.startswith('0x') else private_key)
        priv_key = keys.PrivateKey(private_key_bytes)
        public_key = priv_key.public_key
        
        public_key_hex = public_key.to_hex()
        
        signature = self.client.get_signed_code(msg_to_sign)

        url = 'https://login.saharalabs.ai/v1/auth/login'
        json_data = {
            'message': msg_to_sign,
            'platformType': "DeveloperPortal",
            'pubkey': public_key_hex,
            'role': 7,
            'signature': signature,
            'walletType': "io.rabby"
        }
        response = await self.session.post(url, json=json_data)
        
        data = response.json()
        self.logger.success(f"Token received, proceeding to the next actions...")
        return data['data']['token']
    
    
    async def register_profile(self, jwt):
        if not jwt:
            self.logger.error("Cannot register profile: No SIWA-TOKEN provided")
            return False
        
        with open(names, 'r', encoding="utf-8") as pnames:
            python_names = pnames.read().splitlines()
            
        with open(lastnames, 'r', encoding="utf-8") as lnames:
            last_python_names = lnames.read().splitlines()
            
        with open(countries, 'r', encoding="utf-8") as countr:
            python_countries = countr.read().splitlines()
            
        with open(languages, 'r', encoding="utf-8") as planguag:
            python_languages = planguag.read().splitlines()
            
        name = random.choice(python_names)
        last_name = random.choice(last_python_names)
        country = random.choice(python_countries)
        language = random.choice(python_languages)
        
        url = 'https://login.saharalabs.ai/api/users/v3/profile'
        json_data = {
            "firstName": name,
            "lastName": last_name,
            "gender": "Male",
            "country": country,
            "languages": [language],
        }

        headers = {'Authorization': f'Bearer {jwt}'}
        
        response = await self.session.post(url, json=json_data, headers=headers)
        if response.status_code in (200, 201):
            self.logger.success("Profile registered successfully!")
        return language
    
    
    async def chat_gpt_request(self):
        OPENAI_API_KEY = CONFIG.OPENAI_API_KEY
        try:
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
        except Exception as e:
            self.logger.info(f"Error with connecting to OpenAI: {e}")
        language = await self.check_need_data()
        try:
            gpt_version = "gpt-4o-mini"
            prompt = (f"Hello, write an prompt for AI Learning in {language}, write nothing except this prompt")
            response = client.chat.completions.create(
                model= gpt_version,
                messages=[
                    {"role": "user", "content": prompt}])
            message = response.choices[0].message.content
            self.logger.info(f"Message: {message}")
        except Exception as e:
            self.logger.info(f"Error with connecting to GPT: {e}")
        
        prompts_file = f"{self.client.address}.txt"
        prompt_destination = os.path.join(prompts, prompts_file)
        new_message = message.strip('"')
        
        with open(prompt_destination, "w") as file:
                file.write(new_message)
        
        self.logger.success(f"Message successfully written!")
        
        
    async def create_folder(self):
        jwt = await self.login_request()
        url = 'https://portal.saharalabs.ai/api/vault/create'
        headers = {'Authorization': f'Bearer {jwt}'}
        random_string = ''.join(random.choice(string.ascii_letters) for _ in range(5))
        
        json_data = {
            'name': random_string,
            'description': '',
        }
        
        response = await self.session.post(url, json=json_data, headers=headers)
        data = response.json()
        return data['id']

     
    async def send_file(self, jwt):
        prompts_file = f"{self.client.address}.txt"
        prompt_destination = os.path.join(prompts, prompts_file)
        headers = {'Authorization': f'Bearer {jwt}'}
    
        filename = os.path.basename(prompt_destination)
        file_type = "text/plain"
        file_content = open(prompt_destination, "rb").read()
            
        presigned_resp = await self.session.get(
            "https://portal.saharalabs.ai/api/vault/upload/presigned-url",
            params={
                    "fileName": filename,
                    "fileType": file_type,
                "contextLength": str(len(file_content))
            },
            headers=headers
        )
    
        if presigned_resp.status_code != 200:    
            raise Exception(f"Error with receiving pre-sign: {presigned_resp.status_code} | {await presigned_resp.text()}")
    
        presigned_data = presigned_resp.json()
        upload_url = presigned_data["url"]
        cloud_storage_id = presigned_data["cloudStorageId"]
    
        upload_resp = await self.session.put(upload_url, data=file_content)
        if upload_resp.status_code not in [200, 201]:    
            raise Exception(f"Error with sending file: {upload_resp.status_code}")
    
        self.logger.success("File successfully sent! (Without JSON asnwer!)")
        return cloud_storage_id
    
    
    async def create_dataset(self):
        jwt = await self.login_request()
        cloud_storage_id = await self.send_file(jwt)
        
        vault_id = await self.create_folder()
        url = f'https://portal.saharalabs.ai/api/vault/{vault_id}/datasets/create/without-file'
        headers = {'Authorization': f'Bearer {jwt}', "Content-Type": "application/json"}

        language = await self.check_need_data()
        random_string = ''.join(random.choice(string.ascii_letters) for _ in range(5))

        prompts_file = f"{self.client.address}.txt"
        prompt_destination = os.path.join(prompts, prompts_file)

        with open(prompt_destination, "r") as file:
            read_file = file.read()

        json_data = {
        "cloudstorageId": cloud_storage_id,
        'language': language,
        'modality': 'Text',
        'name': random_string,
        'remarks': "",
        'sample': read_file
    }

        self.logger.info(f"Sending next data: {json_data}")
        response = await self.session.post(url, json=json_data, headers=headers)

        if response.status_code in (200, 201):
            self.logger.success("Dataset successfully created! Let's signing!")
        else:
            self.logger.error(f"Error with dataset creation: {response.status_code} | {response.json()}")
            
        data = response.json()
        
        data_tx = data['data']

        nonce = await self.client.w3.eth.get_transaction_count(self.client.address)

        tx = {
        'nonce': nonce,
        'to': self.client.w3.to_checksum_address("0xf0c871014cb250d991375cf5d6a4a9bc0a82cf5b"),
        'value': 0,
        'gas': 1985520,
        'gasPrice': int("0x8ef4df43", 16),
        'data': data_tx,
        'chainId': int("0x4c7e1", 16)
    }


        signed_tx = self.client.w3.eth.account.sign_transaction(tx, private_key=self.client.key)
        
        tx_hash = await self.client.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        hashh = self.client.w3.to_hex(tx_hash)
        self.logger.info(f"Tx hash: {self.explorer}{hashh}")
        
        new_url = 'https://testnet.saharalabs.ai/'
        
        new_json_data = {
            'method': 'eth_getTransactionReceipt',
            'params': [hashh]
        }
        
        if not hashh == None:
            self.logger.success(f"Successfully signed dataset!")
        
        response = await self.session.post(url=new_url, json=new_json_data)
        

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

