# v1-arbitrageur-bot

Pair arbitrageur bot that arbitrages between Marginal v1 and Uniswap v3 pools.

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

```sh
silverback run "main:app" --network :mainnet:alchemy
```
