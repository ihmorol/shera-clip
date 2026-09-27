"""python -m shera: start the local server on 127.0.0.1 and open the browser."""
import threading
import webbrowser

import uvicorn

from shera import config, pipeline
from shera.app import app


def main():
    pipeline.on_start()  # db.init + ledger recovery + resume running jobs
    url = f"http://{config.HOST}:{config.PORT}/"
    threading.Timer(1.0, webbrowser.open, (url,)).start()
    print(f"Shera Clip: {url}  (data: {config.DATA})")
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="warning")


if __name__ == "__main__":
    main()
