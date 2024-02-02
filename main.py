from typing import Annotated  # NOTE: Only Python 3.9+

from ape import chain
from ape.api import BlockAPI
from taskiq import Context, TaskiqDepends, TaskiqState

from silverback import SilverbackApp, SilverbackStartupState

# Do this to initialize your app
app = SilverbackApp()


@app.on_startup()
def app_startup(startup_state: SilverbackStartupState):
    return {"message": "Starting...", "block_number": startup_state.last_block_seen}


# Can handle some initialization on startup, like models or network connections
@app.on_worker_startup()
def worker_startup(state: TaskiqState):
    state.block_count = 0
    # state.db = MyDB()
    return {"message": "Worker started."}


# This is how we trigger off of new blocks
@app.on_(chain.blocks)
# context must be a type annotated kwarg to be provided to the task
def exec_block(block: BlockAPI, context: Annotated[Context, TaskiqDepends()]):
    context.state.block_count += 1
    return len(block.transactions)


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
