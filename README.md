# v1-arbitrageur-bot

Pair arbitrageur bot that arbitrages between [Marginal v1](https://github.com/MarginalProtocol/v1-core) and [Uniswap v3](https://github.com/uniswap/v3-core) pools.

## Installation

The repo uses [ApeWorX](https://github.com/apeworx/ape) and [Silverback](https://github.com/apeworx/silverback) for development.

Set up a virtual environment

```sh
python -m venv .venv
source .venv/bin/activate
```

Install requirements and Ape plugins

```sh
pip install -r requirements.txt
ape plugins install .
```

## Usage

Include the environment variable for the address of the [`PairArbitrageur`](https://github.com/MarginalProtocol/book/blob/main/src/v1/periphery/contracts/examples/PairArbitrageur.sol/contract.PairArbitrageur.md) example contract
and the address of the [`MarginalV1Pool`](https://github.com/MarginalProtocol/book/blob/main/src/v1/core/contracts/MarginalV1Pool.sol/contract.MarginalV1Pool.md) you wish to watch

```sh
export CONTRACT_ADDRESS_PAIR_ARBITRAGEUR=<address of arb contract on network>
export CONTRACT_ADDRESS_MARGV1_POOL=<address of marginal v1 pool contract on network>
```

Then run silverback


```sh
silverback run "main:app" --network :mainnet:alchemy --account acct-name
```
