#!/usr/bin/env python3
"""
Simple HTTP server for local development
Serves files from the public directory with index.html as default
"""

import http.server
import socketserver
import os
from pathlib import Path

PORT = 3000
PUBLIC_DIR = Path(__file__).parent / "public"

class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)
    
    def end_headers(self):
        # Add CORS headers if needed
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()
    
    def do_GET(self):
        # If path is root or ends with /, try index.html
        if self.path == '/' or self.path.endswith('/'):
            if self.path != '/':
                # Try to serve index.html in that directory
                original_path = self.path
                self.path = original_path.rstrip('/') + '/index.html'
                if not os.path.exists(os.path.join(PUBLIC_DIR, self.path.lstrip('/'))):
                    # If index.html doesn't exist, try without .html extension
                    self.path = original_path.rstrip('/') + '.html'
        elif not self.path.endswith(('.html', '.js', '.css', '.json', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.md', '.pdf')):
            # If path doesn't have extension, try adding .html
            html_path = self.path + '.html'
            if os.path.exists(os.path.join(PUBLIC_DIR, html_path.lstrip('/'))):
                self.path = html_path
        
        return super().do_GET()

if __name__ == "__main__":
    os.chdir(PUBLIC_DIR)
    
    with socketserver.TCPServer(("", PORT), CustomHTTPRequestHandler) as httpd:
        print(f"Server running at http://localhost:{PORT}/")
        print(f"Serving files from: {PUBLIC_DIR}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")

