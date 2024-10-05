# Bittensor Blockchain RPC Subnet

This repository contains a Bittensor subnet implementation for blockchain RPC requests. It includes a miner that serves RPC requests and a validator that queries miners and updates their scores based on their performance.

## Prerequisites

- Python 3.10 or higher
- [Git](https://git-scm.com/)

## Installation

Clone the repository:

```bash
git clone git@github.com:Thoma-Technologies/tenfura.git
cd tenfura
```

## Configuration

1. Create a wallet for your miner and validator:

```bash
btcli wallet new_coldkey --wallet.name mywallet
btcli wallet new_hotkey --wallet.name mywallet --wallet.hotkey miner
btcli wallet new_hotkey --wallet.name mywallet --wallet.hotkey validator
```

2. Register your wallets on the Bittensor network:

```bash
btcli subnet register --wallet.name mywallet --wallet.hotkey miner --subtensor.network <network> --netuid <netuid>
btcli subnet register --wallet.name mywallet --wallet.hotkey validator --subtensor.network <network> --netuid <netuid>
```

## Running the Validator

To run the validator, use the following command:

```bash
./run.sh validator --wallet.name mywallet --wallet.hotkey validator --subtensor.network <network> --netuid <netuid>
```

Replace `<network>` and `<netuid>` with appropriate values.

## Running the Miner

To run the miner, use the following command:

```bash
./run.sh miner --wallet.name mywallet --wallet.hotkey miner --subtensor.network <network> --netuid <netuid> --axon.port <port> --infura_api_key <your_infura_api_key>
```

Replace `<network>`, `<netuid>`, `<port>`, and `<your_infura_api_key>` with appropriate values.

## Customization

You can customize the behavior of the miner and validator by modifying their respective Python files. The main logic for handling blockchain requests is in the `handle_blockchain_request` method of the `Miner` class in `miner.py`.

## Important Note for Miners

The default implementation uses Infura as the RPC provider. However, miners are strongly encouraged to modify the code to use their own node infrastructure. This will provide better control over the RPC requests and responses, potentially improving performance and reliability.

To do this:

1. Modify the `Miner` class in `miner.py` to remove the Infura-specific code.
2. Implement your own RPC request handling logic that connects to your node infrastructure.
3. Ensure that your implementation can handle all the chain types defined in the `Chains` enum in `protocol.py`.

Example of how you might modify the `handle_blockchain_request` method:

```python
def handle_blockchain_request(self, synapse: BlockchainRequest) -> BlockchainRequest:
    try:
        chain = Chains(synapse.chain_id)
        # Replace this with your own node connection logic
        node = self.get_node_for_chain(chain)
        
        # Use your node to process the RPC request
        response = node.process_rpc_request(synapse.payload)
        
        synapse.response = response
    except Exception as e:
        synapse.error = str(e)
    return synapse
```

Remember to implement proper error handling and ensure that your node infrastructure can handle the expected load.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
