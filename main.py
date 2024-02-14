import os
from typing import Annotated  # NOTE: Only Python 3.9+

from ape import chain, Contract
from ape.api import BlockAPI
from taskiq import Context, TaskiqDepends, TaskiqState

from silverback import SilverbackApp, SilverbackStartupState

# Do this to initialize your app
app = SilverbackApp()

# Arbitrageur and pool contracts
arbitrageur = Contract(os.environ["CONTRACT_ADDRESS_PAIR_ARBITRAGEUR"])
mrglv1_pool = Contract(os.environ["CONTRACT_ADDRESS_MRGLV1_POOL"])
univ3_pool = Contract(mrglv1_pool.oracle())

# Price diff above which execute arbitrage
SQRT_PRICE_TOL = os.environ.get("SQRT_PRICE_TOLERANCE", 5e-3)  # default to > 50 bps


@app.on_startup()
def app_startup(startup_state: SilverbackStartupState):
    return {"message": "Starting...", "block_number": startup_state.last_block_seen}


# Can handle some initialization on startup, like models or network connections
@app.on_worker_startup()
def worker_startup(state: TaskiqState):
    state.block_count = 0
    state.arb_count = 0
    state.signer_balance = app.signer.balance

    # check one of the tokens WETH so can get ETH out
    state.token0 = mrglv1_pool.token0()
    state.token1 = mrglv1_pool.token1()
    state.maintenance = mrglv1_pool.maintenance()
    state.oracle = mrglv1_pool.oracle()
    state.WETH9 = arbitrageur.WETH9()

    if state.token0 != state.WETH9 and state.token1 != state.WETH9:
        raise Exception("One of the tokens in pool must be WETH9")

    # TODO: state.db = MyDB() if allow for tracking many pools
    return {"message": "Worker started."}


# This is how we trigger off of new blocks
@app.on_(chain.blocks)
# context must be a type annotated kwarg to be provided to the task
def exec_block(block: BlockAPI, context: Annotated[Context, TaskiqDepends()]):
    # execute arb if price differences beyond tolerance
    univ3_sqrt_price_x96 = univ3_pool.slot0().sqrtPriceX96
    mrglv1_sqrt_price_x96 = mrglv1_pool.state().sqrtPriceX96

    r = univ3_sqrt_price_x96 / mrglv1_sqrt_price_x96 - 1
    if abs(r) > SQRT_PRICE_TOL:
        params = (
            context.state.token0,
            context.state.token1,
            context.state.maintenance,
            context.state.oracle,
            app.signer.address,
            context.state.WETH9,
            0,  # TODO: amount_out_min
            0,  # TODO: sqrt price limit0
            0,  # TODO: sqrt price limit1
            2**256 - 1,  # TODO: deadline,
            True,
        )
        arbitrageur.execute(params, sender=app.signer)  # TODO: try catch if errors
        context.state.arb_count += 1

    context.state.block_count += 1
    context.state.signer_balance = app.signer.balance
    return {
        "block_count": context.state.block_count,
        "arb_count": context.state.arb_count,
        "signer_balance": context.state.signer_balance,
        "univ3_sqrt_price_x96": univ3_sqrt_price_x96,
        "mrglv1_sqrt_price_x96": mrglv1_sqrt_price_x96,
    }


# Just in case you need to release some resources or something
@app.on_worker_shutdown()
def worker_shutdown(state):
    return {
        "message": f"Worker stopped after handling {state.block_count} blocks.",
        "block_count": state.block_count,
    }


# A final job to execute on Silverback shutdown
@app.on_shutdown()
def app_shutdown(state):
    return {"message": "Stopping..."}
