from flask import Flask, request, send_from_directory, jsonify, render_template
from datetime import datetime
import os
import sqlite3
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['PLATE_IMAGES'] = 'plate_images'
app.config['DATABASE'] = 'plates.db'

# Ensure the upload folder exists
os.makedirs(app.config['PLATE_IMAGES'], exist_ok=True)

def init_db():
    """Initialize the SQLite database"""
    with sqlite3.connect(app.config['DATABASE']) as conn:
        conn.execute('''
        CREATE TABLE IF NOT EXISTS plates (
            id TEXT PRIMARY KEY,
            plate_text TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            video_source TEXT NOT NULL,
            image_path TEXT NOT NULL,
            position TEXT NOT NULL,
            frame_num INTEGER NOT NULL
        )
        ''')
        conn.commit()

def log_plate_to_db(plate_data):
    """Log a plate detection to the database"""
    with sqlite3.connect(app.config['DATABASE']) as conn:
        conn.execute('''
        INSERT OR REPLACE INTO plates 
        (id, plate_text, timestamp, video_source, image_path, position, frame_num)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            plate_data['detection_id'],
            plate_data['plate_text'],
            plate_data['timestamp'],
            plate_data['video_source'],
            plate_data['image_path'],
            str(plate_data['position']),
            plate_data['frame_num']
        ))
        conn.commit()

@app.route('/')
def index():
    """Render the web interface"""
    return render_template('index.html')

@app.route('/api/plates')
def get_plates():
    """Get all plate detections"""
    with sqlite3.connect(app.config['DATABASE']) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute('SELECT * FROM plates ORDER BY timestamp DESC')
        plates = cur.fetchall()
    return jsonify([dict(plate) for plate in plates])

@app.route('/api/plates/<plate_id>')
def get_plate(plate_id):
    """Get a specific plate detection"""
    with sqlite3.connect(app.config['DATABASE']) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute('SELECT * FROM plates WHERE id = ?', (plate_id,))
        plate = cur.fetchone()
    if plate:
        return jsonify(dict(plate))
    return jsonify({'error': 'Plate not found'}), 404

@app.route('/images/<path:filename>')
def serve_image(filename):
    """Serve plate images"""
    # Get the date folder from filename (format: YYYY-MM-DD_plate_uuid.jpg)
    date_folder = filename.split('_')[0]
    return send_from_directory(
        os.path.join(app.config['PLATE_IMAGES'], date_folder),
        filename
    )

@app.route('/api/search')
def search_plates():
    """Search plates by text"""
    query = request.args.get('q', '')
    with sqlite3.connect(app.config['DATABASE']) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute('''
            SELECT * FROM plates 
            WHERE plate_text LIKE ? 
            ORDER BY timestamp DESC
        ''', (f'%{query}%',))
        plates = cur.fetchall()
    return jsonify([dict(plate) for plate in plates])

# WebSocket endpoint for real-time updates (optional)
@app.route('/api/updates')
def ws_updates():
    """WebSocket endpoint for real-time updates"""
    if request.environ.get('wsgi.websocket'):
        ws = request.environ['wsgi.websocket']
        # Implement WebSocket communication here
        return "WebSocket endpoint"
    return "WebSocket not supported", 400

if __name__ == '__main__':
    init_db()
    
    # Create template directory if it doesn't exist
    os.makedirs(os.path.join(app.root_path, 'templates'), exist_ok=True)
    
    # Create basic index.html if it doesn't exist
    index_path = os.path.join(app.root_path, 'templates', 'index.html')
    if not os.path.exists(index_path):
        with open(index_path, 'w') as f:
            f.write('''
<!DOCTYPE html>
<html>
<head>
    <title>License Plate Detection</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .plate { border: 1px solid #ddd; padding: 15px; margin-bottom: 10px; border-radius: 5px; }
        .plate img { max-width: 300px; max-height: 150px; }
        .search { margin-bottom: 20px; }
    </style>
</head>
<body>
    <h1>License Plate Detections</h1>
    <div class="search">
        <input type="text" id="search" placeholder="Search plates...">
        <button onclick="searchPlates()">Search</button>
    </div>
    <div id="plates-container"></div>

    <script>
        function loadPlates() {
            fetch('/api/plates')
                .then(response => response.json())
                .then(plates => {
                    const container = document.getElementById('plates-container');
                    container.innerHTML = '';
                    
                    plates.forEach(plate => {
                        const plateDiv = document.createElement('div');
                        plateDiv.className = 'plate';
                        plateDiv.innerHTML = `
                            <h3>${plate.plate_text}</h3>
                            <p>Detected at: ${new Date(plate.timestamp).toLocaleString()}</p>
                            <p>Source: ${plate.video_source} (Frame ${plate.frame_num})</p>
                            <img src="/images/${plate.image_path.split('/').pop()}" alt="${plate.plate_text}">
                        `;
                        container.appendChild(plateDiv);
                    });
                });
        }

        function searchPlates() {
            const query = document.getElementById('search').value;
            fetch(`/api/search?q=${encodeURIComponent(query)}`)
                .then(response => response.json())
                .then(plates => {
                    const container = document.getElementById('plates-container');
                    container.innerHTML = '';
                    
                    plates.forEach(plate => {
                        const plateDiv = document.createElement('div');
                        plateDiv.className = 'plate';
                        plateDiv.innerHTML = `
                            <h3>${plate.plate_text}</h3>
                            <p>Detected at: ${new Date(plate.timestamp).toLocaleString()}</p>
                            <p>Source: ${plate.video_source} (Frame ${plate.frame_num})</p>
                            <img src="/images/${plate.image_path.split('/').pop()}" alt="${plate.plate_text}">
                        `;
                        container.appendChild(plateDiv);
                    });
                });
        }

        // Load plates on page load
        loadPlates();
    </script>
</body>
</html>
            ''')
    
    app.run(host='0.0.0.0', port=8000, debug=True)