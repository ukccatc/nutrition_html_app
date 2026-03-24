import http.server
import socketserver
import webbrowser
import threading
import os
import time

PORT = 8000
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

def start_server():
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Server started at http://localhost:{PORT}")
        print("Press Ctrl+C to stop.")
        httpd.serve_forever()

if __name__ == "__main__":
    # Change to the directory where the script is located
    os.chdir(DIRECTORY)
    
    # Start server in a separate thread
    threading.Thread(target=start_server, daemon=True).start()
    
    # Give it a second to start
    time.sleep(1)
    
    # Open the index.html
    webbrowser.open(f"http://localhost:{PORT}/index.html")
    
    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down server...")
