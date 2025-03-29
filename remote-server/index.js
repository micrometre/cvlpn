const express = require('express');
const bodyParser = require('body-parser');
const fs = require('fs');
const path = require('path');
const { v4: uuidv4 } = require('uuid');
const cors = require('cors');
const morgan = require('morgan');
const helmet = require('helmet');
const WebSocket = require('ws');

const app = express();
const port = process.env.PORT || 5000;

// ======================
// CONFIGURATION
// ======================
const UPLOAD_DIR = 'public/images';
const LOG_FILE = 'alpr_server.log';
const MAX_LOG_AGE_DAYS = 30;
const MAX_RECENT_PLATES = 100; // In-memory store size

// ======================
// SETUP
// ======================
// Ensure directories exist
if (!fs.existsSync(UPLOAD_DIR)) {
  fs.mkdirSync(UPLOAD_DIR, { recursive: true });
}

// In-memory storage for recent plates
const recentPlates = [];
const plateStore = new Map();

// Initialize WebSocket server
const server = app.listen(port, () => {
  console.log(`ALPR server listening on port ${port}`);
});

const wss = new WebSocket.Server({ server });

// Track connected WebSocket clients
const clients = new Set();

wss.on('connection', (ws) => {
  clients.add(ws);
  console.log(`New WebSocket connection. Total clients: ${clients.size}`);

  ws.on('close', () => {
    clients.delete(ws);
    console.log(`WebSocket disconnected. Total clients: ${clients.size}`);
  });
});

// ======================
// MIDDLEWARE
// ======================
app.use(helmet());
app.use(cors());
app.use(bodyParser.json({ limit: '10mb' }));
app.use(bodyParser.urlencoded({ extended: true, limit: '10mb' }));

// Enhanced logging with morgan
app.use(morgan('combined', {
  stream: fs.createWriteStream(path.join(__dirname, 'access.log'), { flags: 'a' })
}));

// ======================
// UTILITY FUNCTIONS
// ======================
function broadcastToClients(data) {
  const message = JSON.stringify(data);
  clients.forEach(client => {
    if (client.readyState === WebSocket.OPEN) {
      client.send(message);
    }
  });
}

function rotateLogs() {
  if (fs.existsSync(LOG_FILE)) {
    const stats = fs.statSync(LOG_FILE);
    const logAgeDays = (Date.now() - stats.birthtimeMs) / (1000 * 60 * 60 * 24);
    
    if (logAgeDays > MAX_LOG_AGE_DAYS) {
      const archiveName = `logs/archive-${new Date().toISOString().replace(/[:.]/g, '-')}.log`;
      fs.renameSync(LOG_FILE, archiveName);
      console.log(`Rotated log file to ${archiveName}`);
    }
  }
}

function storePlate(plateData) {
  // Store the full plate data
  plateStore.set(plateData.uuid, plateData);
  
  // Add to recent plates list
  recentPlates.unshift(plateData.uuid);
  
  // Trim if we exceed maximum
  if (recentPlates.length > MAX_RECENT_PLATES) {
    const removedId = recentPlates.pop();
    plateStore.delete(removedId);
  }
}

// ======================
// API ENDPOINTS
// ======================
// POST endpoint for license plate data
app.post('/api/plates', (req, res) => {
  try {
    const plateData = req.body;
    console.log(plateData)
    
    // Validate required fields
    const requiredFields = ['plate', 'position', 'frame_num', 'image_url'];
    const missingFields = requiredFields.filter(field => !plateData[field]);

    if (missingFields.length > 0) {
      return res.status(400).json({
        error: 'Missing required fields',
        missing: missingFields
      });
    }

    // Enhance data
    plateData.timestamp = plateData.timestamp || new Date().toISOString();
    plateData.uuid = plateData.uuid || uuidv4();
    plateData.server_received = new Date().toISOString();

    // Store in memory
    storePlate(plateData);

    // Broadcast to WebSocket clients
    broadcastToClients({
      type: 'new_plate',
      data: plateData
    });

    // Log the received data
    const logEntry = {
      timestamp: new Date().toISOString(),
      ...plateData
    };

    fs.appendFileSync(LOG_FILE, JSON.stringify(logEntry) + '\n');

    console.log(`Received plate: ${plateData.plate} (${plateData.uuid})`);

    res.status(200).json({
      status: 'success',
      plate: plateData.plate,
      uuid: plateData.uuid,
      timestamp: plateData.timestamp
    });

  } catch (error) {
    console.error('Error processing plate data:', error);
    res.status(500).json({
      error: 'Internal server error',
      details: error.message
    });
  }
});



// WebSocket endpoint for real-time updates
app.get('/api/ws', (req, res) => {
  res.status(400).json({ 
    error: 'Use WebSocket protocol to connect to this endpoint',
    ws_url: `ws://${req.headers.host}`
  });
});


// Health check endpoint
app.get('/health', (req, res) => {
  res.status(200).json({
    status: 'healthy',
    uptime: process.uptime(),
    timestamp: new Date().toISOString(),
    stats: {
      plates_stored: plateStore.size,
      ws_clients: clients.size
    }
  });
});

// 404 handler
app.use((req, res) => {
  res.status(404).json({ error: 'Endpoint not found' });
});

// Log rotation on startup
rotateLogs();

// Cleanup on shutdown
process.on('SIGTERM', () => {
  console.log('Shutting down server...');
  server.close(() => {
    console.log('Server terminated');
    process.exit(0);
  });
});