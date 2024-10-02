import typing
import bittensor as bt

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