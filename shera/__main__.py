"""python -m shera: no arguments starts the local server on 127.0.0.1 and opens the
browser; any arguments (desktop, doctor, jobs, ...) are handled by the CLI, so the
Start-menu shortcuts can be plain `pythonw -m shera [desktop]`."""
import sys
import threading
import webbrowser

import uvicorn

from shera import config, pipeline
from shera.app import app


def main():
    if len(sys.argv) > 1:
        from shera import cli
        raise SystemExit(cli.main(sys.argv[1:]))
    pipeline.on_start()  # db.init + ledger recovery + resume running jobs
    url = f"http://{config.HOST}:{config.PORT}/"
    threading.Timer(1.0, webbrowser.open, (url,)).start()
    print(f"Shera Clip: {url}  (data: {config.DATA})")
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="warning")


if __name__ == "__main__":
    main()
