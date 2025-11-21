# WrestleData.com

## Development Setup

### Port Configuration
The application uses the following ports in development:

- Frontend (Vite): `http://localhost:3000`
- DynamoDB Local: `http://localhost:8001`

### Starting the Application

1. Start DynamoDB Local:
```bash
cd /Users/tjthompson/dynamodb-local
./start_dynamodb_local.sh
```

2. Start the Frontend:
```bash
cd frontend
npm run dev
```

### Troubleshooting

If you encounter port conflicts:

1. Check if ports are in use:
```bash
lsof -i :3000  # Check frontend port
lsof -i :8001  # Check DynamoDB port
```

2. Kill existing processes if needed:
```bash
kill <PID>  # Replace <PID> with the process ID
# or force kill if needed
kill -9 <PID>
``` 