import os

from utils.run_config import ROOT_DIR


SEED_TO_ADDRESS_JS = os.path.join(ROOT_DIR, 'utils', 'js', 'seed_to_address.mjs')
SIGN_MESSAGE_BIP322_JS = os.path.join(ROOT_DIR, 'utils', 'js', 'sign_message_bip322.mjs')
USER_AGENTS = os.path.join(ROOT_DIR, 'utils', 'user_agents.txt')
APPROVE_ABI = os.path.join(ROOT_DIR, 'utils', 'abis', 'approve_abi.json')
BALANCE_OF_ABI = os.path.join(ROOT_DIR, 'utils', 'abis', 'balance_of_abi.json')
DECIMALS_ABI = os.path.join(ROOT_DIR, 'utils', 'abis', 'decimals_abi.json')
ERC20_ABI = os.path.join(ROOT_DIR, 'utils', 'abis', 'erc20_abi.json')
