import os
import time
import argparse
import traceback
import bittensor as bt
from typing import Tuple
from protocol import BlockchainRequest, Chains
import requests


class Miner:
    def __init__(self):
        self.config = self.get_config()
        self.setup_logging()
        self.setup_bittensor_objects()
        self.infura_endpoints = {
            Chains.ETH_MAINNET: f"https://mainnet.infura.io/v3/{self.config.infura_api_key}",
            Chains.ETH_SEPOLIA: f"https://sepolia.infura.io/v3/{self.config.infura_api_key}",
            Chains.LINEA_MAINNET: f"https://linea-mainnet.infura.io/v3/{self.config.infura_api_key}",
            Chains.LINEA_SEPOLIA: f"https://linea-sepolia.infura.io/v3/{self.config.infura_api_key}",
            Chains.POLYGON_MAINNET: f"https://polygon-mainnet.infura.io/v3/{self.config.infura_api_key}",
            Chains.OPTIMISM_MAINNET: f"https://optimism-mainnet.infura.io/v3/{self.config.infura_api_key}",
            Chains.OPTIMISM_SEPOLIA: f"https://optimism-sepolia.infura.io/v3/{self.config.infura_api_key}",
            Chains.ARBITRUM_MAINNET: f"https://arbitrum-mainnet.infura.io/v3/{self.config.infura_api_key}",
            Chains.ARBITRUM_SEPOLIA: f"https://arbitrum-sepolia.infura.io/v3/{self.config.infura_api_key}",
            Chains.AVALANCHE_MAINNET: f"https://avalanche-mainnet.infura.io/v3/{self.config.infura_api_key}",
            Chains.AVALANCHE_FUJI: f"https://avalanche-fuji.infura.io/v3/{self.config.infura_api_key}",
            Chains.BASE_MAINNET: f"https://base-mainnet.infura.io/v3/{self.config.infura_api_key}",
            Chains.BASE_SEPOLIA: f"https://base-sepolia.infura.io/v3/{self.config.infura_api_key}",
            # Add more chains as needed
        }

    def get_config(self):
        # Set up the configuration parser
        parser = argparse.ArgumentParser()

        # TODO: Add your custom miner arguments to the parser.
        parser.add_argument(
            "--infura_api_key",
            type=str,
            help="Infura API key.",
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
        # Adds axon specific arguments.
        bt.axon.add_args(parser)
        # Parse the arguments.
        config = bt.config(parser)
        # Set up logging directory
        config.full_path = os.path.expanduser(
            "{}/{}/{}/netuid{}/{}".format(
                config.logging.logging_dir,
                config.wallet.name,
                config.wallet.hotkey_str,
                config.netuid,
                "miner",
            )
        )
        # Ensure the directory for logging exists.
        os.makedirs(config.full_path, exist_ok=True)
        return config

    def setup_logging(self):
        # Activate Bittensor's logging with the set configurations.
        bt.logging(config=self.config, logging_dir=self.config.full_path)
        bt.logging.info(
            f"Running miner for subnet: {self.config.netuid} on network: {self.config.subtensor.network} with config:"
        )
        bt.logging.info(self.config)

    def setup_bittensor_objects(self):
        # Initialize Bittensor miner objects
        bt.logging.info("Setting up Bittensor objects.")

        # Initialize wallet.
        self.wallet = bt.wallet(config=self.config)
        bt.logging.info(f"Wallet: {self.wallet}")

        # Initialize subtensor.
        self.subtensor = bt.subtensor(config=self.config)
        bt.logging.info(f"Subtensor: {self.subtensor}")

        # Initialize metagraph.
        self.metagraph = self.subtensor.metagraph(self.config.netuid)
        bt.logging.info(f"Metagraph: {self.metagraph}")

        if self.wallet.hotkey.ss58_address not in self.metagraph.hotkeys:
            bt.logging.error(
                f"\nYour miner: {self.wallet} is not registered to chain connection: {self.subtensor} \nRun 'btcli register' and try again."
            )
            exit()
        else:
            # Each miner gets a unique identity (UID) in the network.
            self.my_subnet_uid = self.metagraph.hotkeys.index(
                self.wallet.hotkey.ss58_address
            )
            bt.logging.info(f"Running miner on uid: {self.my_subnet_uid}")

    def blacklist_fn(self, synapse: BlockchainRequest) -> Tuple[bool, str]:
        # Ignore requests from unrecognized entities.
        if synapse.dendrite.hotkey not in self.metagraph.hotkeys:
            bt.logging.trace(
                f"Blacklisting unrecognized hotkey {synapse.dendrite.hotkey}"
            )
            return True, None
        bt.logging.trace(
            f"Not blacklisting recognized hotkey {synapse.dendrite.hotkey}"
        )
        return False, None

    def handle_blockchain_request(
        self, synapse: BlockchainRequest
    ) -> BlockchainRequest:
        try:
            chain = Chains(synapse.chain_id)
            if chain not in self.infura_endpoints:
                raise ValueError(f"Unsupported chain: {synapse.chain_id}")

            endpoint = self.infura_endpoints[chain]
            response = requests.post(endpoint, data=synapse.payload)

            if response.status_code == 200:
                synapse.response = response.text
            else:
                synapse.error = (
                    f"Infura request failed with status {response.status_code}"
                )
        except Exception as e:
            synapse.error = str(e)
        return synapse

    def setup_axon(self):
        # Build and link miner functions to the axon.
        self.axon = bt.axon(wallet=self.wallet, port=self.config.axon.port)

        # Attach functions to the axon.
        bt.logging.info(f"Attaching blockchain request handler to axon.")
        self.axon.attach(
            forward_fn=self.handle_blockchain_request,
            blacklist_fn=self.blacklist_fn,
        )

        # Serve the axon.
        bt.logging.info(
            f"Serving axon on network: {self.config.subtensor.network} with netuid: {self.config.netuid}"
        )
        self.axon.serve(netuid=self.config.netuid, subtensor=self.subtensor)
        bt.logging.info(f"Axon: {self.axon}")

        # Start the axon server.
        bt.logging.info(f"Starting axon server on port: {self.config.axon.port}")
        self.axon.start()

    def run(self):
        self.setup_axon()

        # Keep the miner alive.
        bt.logging.info(f"Starting main loop")
        step = 0
        while True:
            try:
                # Periodically update our knowledge of the network graph.
                if step % 60 == 0:
                    self.metagraph.sync()
                    log = (
                        f"Block: {self.metagraph.block.item()} | "
                        f"Incentive: {self.metagraph.I[self.my_subnet_uid]} | "
                    )
                    bt.logging.info(log)
                step += 1
                time.sleep(1)

            except KeyboardInterrupt:
                self.axon.stop()
                bt.logging.success("Miner killed by keyboard interrupt.")
                break
            except Exception as e:
                bt.logging.error(traceback.format_exc())
                continue


# Run the miner.
if __name__ == "__main__":
    miner = Miner()
    miner.run()
