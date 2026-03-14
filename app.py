import os
import json
import base64
import threading
import anthropic
import pandas as pd
from flask import Flask, render_template, request, jsonify, session
from werkzeug.utils import secure_filename
from automation import TollAutomator

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'pdf'}

automator_instance = None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_toll_data(image_path):
    client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
    with open(image_path, 'rb') as f:
        image_data = base64.standard_b64encode(f.read()).decode('utf-8')
    ext = image_path.rsplit('.', 1)[1].lower()
    media_type = 'image/jpeg' if ext in ['jpg', 'jpeg'] else 'image/png'
    prompt = """Analyse this Linkt/CityLink toll invoice and extract ALL fields.
    Return ONLY a valid JSON object with these exact keys (use null if not found):
    {
        "notice_number": "toll invoice number",
        "vehicle_registration": "number plate / rego",
        "vehicle_state": "state of registration e.g. VIC",
        "toll_date": "date of toll in DD/MM/YYYY",
        "toll_time": "time of toll",
        "toll_location": "name of toll point or road",
        "amount_owing": "dollar amount e.g. 45.20",
        "due_date": "payment/nomination due date in DD/MM/YYYY",
        "infringement_number": "if present, the infringement number"
    }
    Return ONLY the JSON, no explanation."""
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
            {"type": "text", "text": prompt}
        ]}]
    )
    text = message.content[0].text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    return json.loads(text)

def lookup_driver(rego, csv_path='drivers.csv'):
    if not os.path.exists(csv_path):
        return None
    df = pd.read_csv(csv_path)
    df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]
    match = df[df['registration'].str.upper().str.strip() == rego.upper().strip()]
    if match.empty:
        return None
    return match.iloc[0].to_dict()

def load_nominator(csv_path='nominator.csv'):
    """Load nominator (vehicle owner) details from CSV — uses first row."""
    if not os.path.exists(csv_path):
        return {"first_name": "", "last_name": ""}
    df = pd.read_csv(csv_path)
    df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]
    if df.empty:
        return {"first_name": "", "last_name": ""}
    return df.iloc[0].to_dict()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'invoice' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['invoice']
    if not file or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Use JPG, PNG.'}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    try:
        toll_data = extract_toll_data(filepath)
    except Exception as e:
        return jsonify({'error': f'Could not read invoice: {str(e)}'}), 500
    rego = toll_data.get('vehicle_registration', '')
    driver_data = lookup_driver(rego) if rego else None
    nominator_data = load_nominator()
    return jsonify({'toll': toll_data, 'driver': driver_data, 'nominator': nominator_data})

@app.route('/start-automation', methods=['POST'])
def start_automation():
    global automator_instance
    data = request.json
    toll = data.get('toll', {})
    driver = data.get('driver', {})
    nominator = data.get('nominator', {})
    print(f"[App] toll={toll}")
    print(f"[App] driver={driver}")
    print(f"[App] nominator={nominator}")
    try:
        automator_instance = TollAutomator()
        thread = threading.Thread(
            target=automator_instance.fill_nomination_form,
            args=(toll, driver, nominator)
        )
        thread.daemon = True
        thread.start()
        return jsonify({'status': 'started'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/automation-status')
def automation_status():
    global automator_instance
    if automator_instance is None:
        return jsonify({'status': 'idle'})
    return jsonify(automator_instance.get_status())

@app.route('/submit-form', methods=['POST'])
def submit_form():
    global automator_instance
    if automator_instance is None:
        return jsonify({'error': 'No active automation session'}), 400
    try:
        automator_instance.submit()
        return jsonify({'status': 'submitted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/cancel-automation', methods=['POST'])
def cancel_automation():
    global automator_instance
    if automator_instance:
        automator_instance.cancel()
        automator_instance = None
    return jsonify({'status': 'cancelled'})

@app.route('/nominator', methods=['GET'])
def get_nominator():
    return jsonify(load_nominator())

@app.route('/nominator', methods=['POST'])
def save_nominator():
    data = request.json
    df = pd.DataFrame([data])
    df.to_csv('nominator.csv', index=False)
    return jsonify({'status': 'saved'})

if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    app.run(debug=True, port=5000)
