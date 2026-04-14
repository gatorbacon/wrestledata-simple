#!/usr/bin/env node
/**
 * Simple static file server for local development
 * Serves files from the public directory with index.html as default
 */

import { createServer } from 'http';
import { readFile, stat } from 'fs/promises';
import { join, extname, normalize } from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const PORT = 3000;
const PUBLIC_DIR = join(__dirname, 'public');

// MIME types
const MIME_TYPES = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.md': 'text/markdown',
  '.pdf': 'application/pdf',
};

async function serveFile(filePath, res) {
  try {
    const stats = await stat(filePath);
    if (!stats.isFile()) {
      return false;
    }

    const ext = extname(filePath).toLowerCase();
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';
    
    const content = await readFile(filePath);
    
    res.writeHead(200, {
      'Content-Type': contentType,
      'Content-Length': content.length,
    });
    res.end(content);
    return true;
  } catch (error) {
    return false;
  }
}

async function handleRequest(req, res) {
  let pathname = new URL(req.url, `http://${req.headers.host}`).pathname;
  
  // Default to index.html for root
  if (pathname === '/') {
    pathname = '/index.html';
  }
  
  // Remove leading slash and normalize
  let filePath = join(PUBLIC_DIR, pathname.slice(1));
  filePath = normalize(filePath);
  
  // Security: ensure file is within public directory
  if (!filePath.startsWith(PUBLIC_DIR)) {
    res.writeHead(403);
    res.end('Forbidden');
    return;
  }
  
  // Try to serve the file
  const served = await serveFile(filePath, res);
  
  if (!served) {
    // If file doesn't exist and path doesn't have extension, try adding .html
    if (!extname(filePath)) {
      const htmlPath = filePath + '.html';
      const htmlServed = await serveFile(htmlPath, res);
      if (htmlServed) {
        return;
      }
    }
    
    // If still not found, try index.html in that directory
    if (pathname.endsWith('/')) {
      const indexPath = join(filePath, 'index.html');
      const indexServed = await serveFile(indexPath, res);
      if (indexServed) {
        return;
      }
    }
    
    // 404
    res.writeHead(404);
    res.end('Not Found');
  }
}

const server = createServer(handleRequest);

server.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}/`);
  console.log(`Serving files from: ${PUBLIC_DIR}`);
});

