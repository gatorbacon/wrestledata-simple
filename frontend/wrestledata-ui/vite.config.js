import { defineConfig } from 'vite'
import { resolve } from 'path'

export default defineConfig({
  server: {
    fs: {
      // Allow Vite to serve files from mt/
      allow: [
        resolve(__dirname, 'public'),
        resolve(__dirname, '../../mt')
      ]
    }
  }
})