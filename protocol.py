import typing
from enum import Enum
import bittensor as bt


class Chains(Enum):
    ETH_MAINNET = "eth-mainnet"
    ETH_SEPOLIA = "eth-sepolia"
    LINEA_MAINNET = "linea-mainnet"
    LINEA_SEPOLIA = "linea-sepolia"
    POLYGON_MAINNET = "polygon-mainnet"
    OPTIMISM_MAINNET = "optimism-mainnet"
    OPTIMISM_SEPOLIA = "optimism-sepolia"
    ARBITRUM_MAINNET = "arbitrum-mainnet"
    ARBITRUM_SEPOLIA = "arbitrum-sepolia"
    AVALANCHE_MAINNET = "avalanche-mainnet"
    AVALANCHE_FUJI = "avalanche-fuji"
    BASE_MAINNET = "base-mainnet"
    BASE_SEPOLIA = "base-sepolia"

class BlockchainRequest(bt.Synapse):
    """
    A protocol for generic blockchain requests between
    the validator (proxy) and the miner.
    """

    # Required request input, filled by the dendrite caller (validator).
    chain_id: str
    payload: str

    # Optional request output, filled by the axon responder (miner).
    response: typing.Optional[str] = None
    error: typing.Optional[str] = None