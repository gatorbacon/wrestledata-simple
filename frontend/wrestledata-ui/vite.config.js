import { defineConfig } from 'vite'
import { resolve } from 'path'

export default defineConfig({
  server: {
    fs: {
      // Allow Vite to serve files from mt/ and data/
      // Include parent directories to allow symlinks to work
      allow: [
        resolve(__dirname, 'public'),
        resolve(__dirname, '../../mt'),
        resolve(__dirname, '../../data'),
        resolve(__dirname, '../..'), // Allow parent directory for symlinks
        resolve(__dirname, '../../..') // Allow project root
      ]
    }
  }
})