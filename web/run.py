"""Launch the PocketPricer web app."""
import os
import sys
import socket
import threading
import time
import webbrowser

# Railway (and other PaaS) set PORT in the environment
PORT       = int(os.environ.get("PORT", 8080))
IS_RAILWAY = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PROJECT_ID"))


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def wait_for_server(port, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        if port_in_use(port):
            return True
        time.sleep(0.3)
    return False


def open_browser():
    print("Waiting for server to be ready...", flush=True)
    if wait_for_server(PORT):
        print(f"Server ready — opening http://localhost:{PORT}", flush=True)
        webbrowser.open(f"http://localhost:{PORT}")
    else:
        print(f"Server did not start in time. Open http://localhost:{PORT} manually.", flush=True)


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    import uvicorn

    if IS_RAILWAY:
        # Running on Railway — no browser, no port conflict check
        print(f"Starting PocketPricer on port {PORT}", flush=True)
    else:
        # Local run
        if port_in_use(PORT):
            print(f"Port {PORT} is already in use. Kill the process using it or change the port.", flush=True)
            sys.exit(1)
        print(f"Starting PocketPricer on http://localhost:{PORT}", flush=True)
        threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run("backend.main:app", host="0.0.0.0", port=PORT)
