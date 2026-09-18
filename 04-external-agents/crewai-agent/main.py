"""Entry point.

Run it instrumented — that is the whole of module 04's wiring:

    amp-instrument python main.py

Running it bare works too; it just produces no traces.
"""

import os

import uvicorn

from agent import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
