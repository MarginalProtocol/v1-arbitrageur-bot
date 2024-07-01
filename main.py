import click
import os
from typing import Annotated  # NOTE: Only Python 3.9+

from ape import chain, Contract
from ape.api import BlockAPI
from ape.exceptions import ContractLogicError
from taskiq import Context, TaskiqDepends, TaskiqState

from silverback import SilverbackApp, SilverbackStartupState

# Do this to initialize your app
app = SilverbackApp()

# Arbitrageur and pool contracts
arbitrageur = Contract(os.environ["CONTRACT_ADDRESS_PAIR_ARBITRAGEUR"])
mrglv1_pool = Contract(os.environ["CONTRACT_ADDRESS_MARGV1_POOL"])
univ3_pool = Contract(mrglv1_pool.oracle())

# Price diff above which execute arbitrage
SQRT_PRICE_TOL = os.environ.get(
    "SQRT_PRICE_TOLERANCE", 25e-4
)  # default to > 50 bps in price

# Slippage limits when execute arbitrage
# TODO: SQRT_PRICE_SLIPPAGE = os.environ.get("SQRT_PRICE_SLIPPAGE", 0)

# Buffer to add to gas cost estimate for transaction: gas_cost *= 1 + BUFFER
GAS_COST_BUFFER = os.environ.get("GAS_COST_BUFFER", 0.125)

# Amount out minimum premium in ETH after gas costs
AMOUNT_OUT_MIN_ETH = os.environ.get("AMOUNT_OUT_MIN_ETH", 0)

# Seconds until deadline from last block handled
SECONDS_TIL_DEADLINE = os.environ.get("SECONDS_TIL_DEADLINE", 600)  # 10 min

# Whether to execute transaction through private mempool
TXN_PRIVATE = os.environ.get("TXN_PRIVATE", True)

# Required confirmations to wait for transaction to go through
TXN_REQUIRED_CONFIRMATIONS = os.environ.get("TXN_REQUIRED_CONFIRMATIONS", 0)


# Gets the desired timestamp deadline for arbitrage execution
def _get_deadline(block: BlockAPI, context: Annotated[Context, TaskiqDepends()]):
    return block.timestamp + SECONDS_TIL_DEADLINE


@app.on_startup()
def app_startup(startup_state: SilverbackStartupState):
    # set up autosign if desired
    if click.confirm("Enable autosign?"):
        app.signer.set_autosign(enabled=True)

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

    click.echo(f"Uniswap v3 sqrt price X96: {univ3_sqrt_price_x96}")
    click.echo(f"Marginal v1 sqrt price X96: {mrglv1_sqrt_price_x96}")
    click.echo(f"Relative difference in sqrt price X96 values: {r}")

    if abs(r) > SQRT_PRICE_TOL:
        amount_out_min = AMOUNT_OUT_MIN_ETH
        deadline = _get_deadline(block, context)
        params = (
            context.state.token0,
            context.state.token1,
            context.state.maintenance,
            context.state.oracle,
            app.signer.address,
            context.state.WETH9,
            amount_out_min,
            0,  # TODO: sqrt price limit0
            0,  # TODO: sqrt price limit1
            deadline,
            True,
        )

        # preview before sending in case of revert
        try:
            gas_cost = arbitrageur.execute.estimate_gas_cost(params, sender=app.signer)
            gas_cost = int(gas_cost * (1 + GAS_COST_BUFFER))
            click.echo(f"Estimated gas cost with buffer: {gas_cost}")

            # update params min ETH amount out
            amount_out_min_index = 6
            params[amount_out_min_index] += gas_cost
            click.echo(f"Amount out min with gas cost: {params[amount_out_min_index]}")

            # preview again in gas of revert with amount out min updated
            click.echo("Checking can submit arbitrage transaction with params ...")
            arbitrageur.execute.estimate_gas_cost(params, sender=app.signer)

            # fire off the transaction
            click.echo(f"Submitting arbitrage transaction with params: {params}")
            arbitrageur.execute(
                params,
                sender=app.signer,
                private=TXN_PRIVATE,
                required_confirmations=TXN_REQUIRED_CONFIRMATIONS,
            )
            context.state.arb_count += 1
        except ContractLogicError as err:
            click.secho(
                f"Contract logic error when estimating gas: {err}",
                blink=True,
                bold=True,
            )

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
