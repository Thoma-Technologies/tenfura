import asyncio
import os
import json
import websockets
import argparse
import traceback
import bittensor as bt
import bittensor.utils as btu
from substrateinterface import SubstrateInterface
from protocol import BlockchainRequest
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
        self.tempo = self.node_query("SubtensorModule", "Tempo", [self.config.netuid])
        self.moving_avg_scores = [1.0] * len(self.metagraph.S)
        self.alpha = 0.1
        self.node = SubstrateInterface(url=self.config.subtensor.chain_endpoint)
        self.miner_responses = defaultdict(
            lambda: {"last_request_time": 0, "total_requests": 0, "total_responses": 0}
        )
        self.query_miners_count = 10  # Number of miners to query for each request

    def get_config(self):
        # Set up the configuration parser.
        parser = argparse.ArgumentParser()
        # TODO: Add your custom validator arguments to the parser.
        parser.add_argument(
            "--custom",
            default="my_custom_value",
            help="Adds a custom value to the parser.",
        )
        # Adds override arguments for network and netuid.
        parser.add_argument(
            "--netuid", type=int, default=1, help="The chain subnet uid."
        )
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
                "validator",
            )
        )
        # Ensure the logging directory exists.
        os.makedirs(config.full_path, exist_ok=True)
        return config

    def setup_logging(self):
        # Set up logging.
        bt.logging(config=self.config, logging_dir=self.config.full_path)
        bt.logging.info(
            f"Running validator for subnet: {self.config.netuid} on network: {self.config.subtensor.network} with config:"
        )
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
            bt.logging.error(
                f"\nYour validator: {self.wallet} is not registered to chain connection: {self.subtensor} \nRun 'btcli register' and try again."
            )
            exit()
        else:
            # Each validator gets a unique identity (UID) in the network.
            self.my_subnet_uid = self.metagraph.hotkeys.index(
                self.wallet.hotkey.ss58_address
            )
            bt.logging.info(f"Running validator on uid: {self.my_subnet_uid}")

        # Set up initial scoring weights for validation.
        bt.logging.info("Building validation weights.")
        self.scores = [1.0] * len(self.metagraph.S)
        bt.logging.info(f"Weights: {self.scores}")

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

        uri = f"wss://app.tenfura.thoma.tech/v1/ws"
        while True:
            try:
                async with websockets.connect(uri) as websocket:
                    bt.logging.info("Connected to entrypoint server")
                    while True:
                        try:
                            request = await websocket.recv()
                            synapse = BlockchainRequest(**json.loads(request))

                            # Process the request (similar to the previous handle_request function)
                            miner_uids = get_random_uids(
                                self.metagraph,
                                self.query_miners_count,
                                100,
                                exclude=[self.my_uid],
                            )
                            axons = [self.metagraph.axons[uid] for uid in miner_uids]
                            responses = self.dendrite.query(
                                axons=axons,
                                synapse=synapse,
                                deserialize=True,
                                timeout=12,
                            )
                            # Update miner responses and scores
                            current_time = time.time()
                            for idx, uid in enumerate(miner_uids):
                                self.miner_responses[uid][
                                    "last_request_time"
                                ] = current_time
                                self.miner_responses[uid]["total_requests"] += 1
                                response = responses[idx]
                                if response is not None:
                                    self.miner_responses[uid]["total_responses"] += 1

                            if responses and any(r is not None for r in responses):
                                valid_response = next(
                                    r for r in responses if r is not None
                                )
                                if valid_response.error:
                                    await websocket.send(
                                        json.dumps({"error": valid_response.error})
                                    )
                                else:
                                    await websocket.send(valid_response.response)
                            else:
                                await websocket.send(
                                    json.dumps({"error": "Internal error"})
                                )

                            # Update scores based on miner responses
                            for uid in range(len(self.metagraph.S)):
                                miner_data = self.miner_responses[uid]
                                if miner_data["total_requests"] > 0:
                                    current_score = (
                                        miner_data["total_responses"]
                                        / miner_data["total_requests"]
                                    )
                                else:
                                    current_score = 1
                                self.moving_avg_scores[uid] = (
                                    1 - self.alpha
                                ) * self.moving_avg_scores[
                                    uid
                                ] + self.alpha * current_score

                            bt.logging.info(
                                f"Moving Average Scores: {self.moving_avg_scores}"
                            )

                            self.current_block = self.node_query("System", "Number", [])
                            last_updates = self.node_query(
                                "SubtensorModule",
                                "LastUpdate",
                                [self.config.netuid],
                            )
                            if self.my_uid in last_updates:
                                self.last_update = (
                                    self.current_block - last_updates[self.my_uid]
                                )
                            else:
                                self.last_update = self.tempo + 2

                            # set weights once every tempo + 1
                            if self.last_update > self.tempo + 1:
                                total = sum(self.moving_avg_scores)
                                weights = [
                                    score / total for score in self.moving_avg_scores
                                ]
                                bt.logging.info(f"Setting weights: {weights}")
                                # Update the incentive mechanism on the Bittensor blockchain.
                                result = self.subtensor.set_weights(
                                    netuid=self.config.netuid,
                                    wallet=self.wallet,
                                    uids=self.metagraph.uids,
                                    weights=weights,
                                    wait_for_inclusion=True,
                                )
                                self.metagraph.sync()

                        except websockets.exceptions.ConnectionClosed:
                            bt.logging.warning(
                                "Connection to entrypoint server closed. Attempting to reconnect..."
                            )
                            break  # Break the inner loop to attempt reconnection

            except (OSError, websockets.exceptions.WebSocketException) as e:
                bt.logging.error(f"Failed to connect to entrypoint server: {e}")
                bt.logging.info("Waiting before attempting to reconnect...")
                await asyncio.sleep(
                    10
                )  # Wait for 10 seconds before attempting to reconnect

            except RuntimeError as e:
                bt.logging.error(f"Runtime error: {e}")
                traceback.print_exc()

            except KeyboardInterrupt:
                bt.logging.success("Keyboard interrupt detected. Exiting validator.")
                return

            # No need for the sleep here, as it's handled by the connection attempt


async def main():
    validator = Validator()
    await validator.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        bt.logging.success("Keyboard interrupt detected. Exiting validator.")
