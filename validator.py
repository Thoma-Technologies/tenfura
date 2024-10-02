import asyncio
import os
import random
import argparse
import traceback
import bittensor as bt
from substrateinterface import SubstrateInterface
from protocol import BlockchainRequest
from fastapi import FastAPI, Request
from fastapi.responses import Response
import uvicorn
from utils.uids import get_random_uids
from collections import defaultdict
import time

class Validator:
    def __init__(self):
        self.config = self.get_config()
        self.setup_logging()
        self.setup_bittensor_objects()
        self.last_update = 0
        self.my_uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
        self.scores = [1.0] * len(self.metagraph.S)
        self.last_update = 0
        self.current_block = 0
        self.tempo = self.node_query('SubtensorModule', 'Tempo', [self.config.netuid])
        self.moving_avg_scores = [1.0] * len(self.metagraph.S)
        self.alpha = 0.1
        self.node = SubstrateInterface(url=self.config.subtensor.chain_endpoint)
        self.app = FastAPI()
        self.setup_routes()
        self.miner_responses = defaultdict(lambda: {
            "last_request_time": 0,
            "total_requests": 0,
            "total_responses": 0
        })
        self.query_miners_count = 10  # Number of miners to query for each request

    def get_config(self):
        # Set up the configuration parser.
        parser = argparse.ArgumentParser()
        # TODO: Add your custom validator arguments to the parser.
        parser.add_argument('--custom', default='my_custom_value', help='Adds a custom value to the parser.')
        # Adds override arguments for network and netuid.
        parser.add_argument('--netuid', type=int, default=1, help="The chain subnet uid.")
        # Adds subtensor specific arguments.
        bt.subtensor.add_args(parser)
        # Adds logging specific arguments.
        bt.logging.add_args(parser)
        # Adds wallet specific arguments.
        bt.wallet.add_args(parser)
        # Parse the config.
        config = bt.config(parser)
        # Set up logging directory.
        config.full_path = os.path.expanduser(
            "{}/{}/{}/netuid{}/{}".format(
                config.logging.logging_dir,
                config.wallet.name,
                config.wallet.hotkey_str,
                config.netuid,
                'validator',
            )
        )
        # Ensure the logging directory exists.
        os.makedirs(config.full_path, exist_ok=True)
        return config

    def setup_logging(self):
        # Set up logging.
        bt.logging(config=self.config, logging_dir=self.config.full_path)
        bt.logging.info(f"Running validator for subnet: {self.config.netuid} on network: {self.config.subtensor.network} with config:")
        bt.logging.info(self.config)

    def setup_bittensor_objects(self):
        # Build Bittensor validator objects.
        bt.logging.info("Setting up Bittensor objects.")

        # Initialize wallet.
        self.wallet = bt.wallet(config=self.config)
        bt.logging.info(f"Wallet: {self.wallet}")

        # Initialize subtensor.
        self.subtensor = bt.subtensor(config=self.config)
        bt.logging.info(f"Subtensor: {self.subtensor}")

        # Initialize dendrite.
        self.dendrite = bt.dendrite(wallet=self.wallet)
        bt.logging.info(f"Dendrite: {self.dendrite}")

        # Initialize metagraph.
        self.metagraph = self.subtensor.metagraph(self.config.netuid)
        bt.logging.info(f"Metagraph: {self.metagraph}")

        # Connect the validator to the network.
        if self.wallet.hotkey.ss58_address not in self.metagraph.hotkeys:
            bt.logging.error(f"\nYour validator: {self.wallet} is not registered to chain connection: {self.subtensor} \nRun 'btcli register' and try again.")
            exit()
        else:
            # Each validator gets a unique identity (UID) in the network.
            self.my_subnet_uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
            bt.logging.info(f"Running validator on uid: {self.my_subnet_uid}")

        # Set up initial scoring weights for validation.
        bt.logging.info("Building validation weights.")
        self.scores = [1.0] * len(self.metagraph.S)
        bt.logging.info(f"Weights: {self.scores}")

    def setup_routes(self):
        @self.app.post("/{chain_id}")
        async def handle_request(chain_id: str, request: Request):
            payload = await request.body()
            synapse = BlockchainRequest(
                chain_id=chain_id,
                payload=payload.decode()
            )

            # Broadcast the query to multiple miners on the network.
            miner_uids = get_random_uids(self.metagraph, self.query_miners_count, 100, exclude=[self.my_uid])
            axons = [self.metagraph.axons[uid] for uid in miner_uids]
            responses = self.dendrite.query(
                axons=axons,
                synapse=synapse,
                deserialize=True,
                timeout=12
            )

            current_time = time.time()
            for idx, uid in enumerate(miner_uids):
                self.miner_responses[uid]["last_request_time"] = current_time
                self.miner_responses[uid]["total_requests"] += 1
                response = responses[idx]
                if response is not None:
                    self.miner_responses[uid]["total_responses"] += 1

            if responses and any(r is not None for r in responses):
                valid_response = next(r for r in responses if r is not None)
                if valid_response.error:
                    return Response(content=valid_response.error, status_code=500)
                else:
                    return Response(content=valid_response.response)
            else:
                return Response(content="Internal error", status_code=500)

    def node_query(self, module, method, params):
        try:
            result = self.node.query(module, method, params).value

        except Exception:
            # reinitilize node
            self.node = SubstrateInterface(url=self.config.subtensor.chain_endpoint)
            result = self.node.query(module, method, params).value
        
        return result

    async def run(self):
        # The Main Validation Loop.
        bt.logging.info("Starting validator loop.")
        while True:
            try:
                # Update scores based on miner responses
                for uid in range(len(self.metagraph.S)):
                    miner_data = self.miner_responses[uid]
                    if miner_data["total_requests"] > 0:
                        current_score = miner_data["total_responses"] / miner_data["total_requests"]
                    else:
                        current_score = 1
                    self.moving_avg_scores[uid] = (1 - self.alpha) * self.moving_avg_scores[uid] + self.alpha * current_score

                bt.logging.info(f"Moving Average Scores: {self.moving_avg_scores}")

                self.current_block = self.node_query('System', 'Number', [])
                self.last_update = self.current_block - self.node_query('SubtensorModule', 'LastUpdate', [self.config.netuid])[self.my_uid]

                # set weights once every tempo + 1
                if self.last_update > self.tempo + 1:
                    total = sum(self.moving_avg_scores)
                    weights = [score / total for score in self.moving_avg_scores]
                    bt.logging.info(f"Setting weights: {weights}")
                    # Update the incentive mechanism on the Bittensor blockchain.
                    result = self.subtensor.set_weights(
                        netuid=self.config.netuid,
                        wallet=self.wallet,
                        uids=self.metagraph.uids,
                        weights=weights,
                        wait_for_inclusion=True
                    )
                    self.metagraph.sync()

            except RuntimeError as e:
                bt.logging.error(e)
                traceback.print_exc()

            except KeyboardInterrupt:
                bt.logging.success("Keyboard interrupt detected. Exiting validator.")
                exit()

            # Sleep for a short duration before the next iteration
            await asyncio.sleep(60)  # Sleep for 1 minute

async def main():
    validator = Validator()
    server = uvicorn.Server(uvicorn.Config(validator.app, host="0.0.0.0", port=8000))
    await asyncio.gather(validator.run(), server.serve())

if __name__ == "__main__":
    asyncio.run(main())