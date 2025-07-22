## A decentralized subnet template for Hypertensor.

The Hypertensor Subnet Template includes all the core components required to launch a decentralized AI application, including:
- **Kademlia DHT (KAD-DHT)** – for scalable, decentralized storage and routing
- **Asyncio-based DHT Node** – designed for fast, concurrent communications
- **DHT Protocol** – allows DHT nodes to request keys/neighbors from other DHT nodes, and manages routing tables
- **DHT Record Storage** – with support for versioned and validated records with customizable predicate extensions
- **Record Validators** – attach custom validation logic to any stored record, such as key authentication and Pydantic schemas
- **DHT Traversal Tools** – Traverse the DHT graph
- **Routing Tables** – manage network topology and neighbor nodes. A data structure that contains DHT peers bucketed according to their distance to node_id. Follows Kademlia routing table
- **P2P Servicer Base** – register RPC methods to the DHT for nodes to call on one another
- **Proof-of-Stake Integration** – incentivize and secure participation
- **Hypertensor Consensus** – Ready to run in parallel to the Hypertensor consensus mechanism
- **Substrate Integration** – Connect to Hypertensor with an RPC endpoint
- **Secure Communication** – support for Ed25519 and RSA authentication for communication

> 💡 Focus on Logic, Not Plumbing
> The networking, cryptography, consensus, and storage layers are already handled. As a subnet builder, your only responsibility is to implement the application logic — the custom AI protocols and behaviors that live on top of the DHT.

## Full Documentation

https://docs.hypertensor.org

## Installation From source

### From source

To install this container from source, simply run the following:

```
git clone https://github.com/hypertensor-blockchain/mesh.git
cd mesh
python -m venv .venv
source .venv/bin/activate
pip install .
```

If you would like to verify that your installation is working properly, you can install with `pip install .[dev]`
instead. Then, you can run the tests with `pytest tests/`.

By default, the contatiner uses the precompiled binary of
the [go-libp2p-daemon](https://github.com/hypertensor-blockchain/go-libp2p-daemon) library. If you face compatibility issues
or want to build the binary yourself, you can recompile it by running `pip install . --global-option="--buildgo"`.
Before running the compilation, please ensure that your machine has a recent version
of [Go toolchain](https://golang.org/doc/install) (1.15 or 1.16 are supported).

### System requirements

- __Linux__ is the default OS for which the container is developed and tested. We recommend Ubuntu 18.04+ (64-bit), but
  other 64-bit distros should work as well. Legacy 32-bit is not recommended.
- __macOS__ is partially supported.
  If you have issues, you can run the container using [Docker](https://docs.docker.com/desktop/mac/install/) instead.
  We recommend using [our Docker image](https://hub.docker.com/r/hypertensor-blockchain/mesh).
- __Windows 10+ (experimental)__ can run the container
  using [WSL](https://docs.microsoft.com/ru-ru/windows/wsl/install-win10). You can configure WSL to use GPU by
  following sections 1–3 of [this guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html) by NVIDIA. After
  that, you can simply follow the instructions above to install with pip or from source.

---

## Documentation

##### Generate private keys

  - This will create 3 private key files for your peer
      - `peer_id`: Main peer ID for communication and signing
      - `bootstrap_peer_id`: (Optional usage) Peer ID to be used as a bootstrap node.
      - `client_peer_id`: (Optional usage) Peer ID to be used as a client. This is for those who want to build frontends to interact with the subnet.

##### Register & Stake on Hypertensor
  - Call `register_subnet_node`
  - Retrieve your `start_epoch` by querying your SubnetNodesData storage element on polkadot.js with your subnet node ID. This is the epoch you must activate your node on + the grace period

### Run node 
*Fill in how to start and run a node for your subnet!*

##### Activate node
  - Call `activate_subnet_node` in Hypertensor on your start epoch up to the grace period.

##### Start Node
```bash
Command to start node
```

---

## Future

- Migrate to py-libp2p over the go-libp2p-daemon once py-libp2p is productionized.

---

## Contributing

This is currently at the active development stage, and we welcome all contributions. Everything, from bug fixes and documentation improvements to entirely new features, is appreciated.

If you want to contribute to this mesh template but don't know where to start, take a look at the unresolved [issues](https://github.com/hypertensor-blockchain/mesh/issues). 

Open a new issue or join [our chat room](https://discord.gg/bY7NUEweQp) in case you want to discuss new functionality or report a possible bug. Bug fixes are always welcome, but new features should be preferably discussed with maintainers beforehand.