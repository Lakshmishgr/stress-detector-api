from flask import Flask, request, jsonify
import sqlite3
import numpy as np
import os

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('stress_data.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS daily_telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT,
            screen_on_time_minutes INTEGER,
            unlock_count INTEGER,
            night_usage_minutes INTEGER,
            step_count INTEGER,
            backspace_count INTEGER DEFAULT 0,
            avg_typing_speed_ms INTEGER DEFAULT 0,
            stress_score INTEGER DEFAULT 50,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def generate_ai_counselor_advice(score, screen, night, steps, backspaces):
    if score < 40:
        status = "Low Stress (Optimal Balance)"
        advice = "Your cognitive load and physical interaction patterns look balanced. Keep up your healthy movement and rest cycles!"
    elif score < 70:
        status = "Moderate Stress (Elevated Load)"
        advice = f"Noticeable friction detected. Backspacing rate ({backspaces} edits) and screen activity suggest mild cognitive load. Take a 5-minute screen break."
    else:
        status = "High Stress (Digital Overload)"
        advice = f"Alert: Elevated stress index ({score}/100). High typing friction combined with {screen}m screen time and {steps} steps. Do 2 minutes of box-breathing now."
    return status, advice

def calculate_stress_index(device_id, screen, unlocks, night, steps, backspaces):
    conn = get_db_connection()
    history = conn.execute(
        '''SELECT screen_on_time_minutes, unlock_count, night_usage_minutes, step_count, backspace_count 
           FROM daily_telemetry WHERE device_id = ? ORDER BY id DESC LIMIT 14''',
        (device_id,)
    ).fetchall()
    conn.close()

    if len(history) < 3:
        screen_m, screen_s = 240.0, 60.0
        unlock_m, unlock_s = 50.0, 15.0
        night_m, night_s = 30.0, 20.0
        step_m, step_s = 5000.0, 1500.0
        backspace_m, backspace_s = 15.0, 5.0
    else:
        screens = [row['screen_on_time_minutes'] for row in history]
        unlocks_list = [row['unlock_count'] for row in history]
        nights = [row['night_usage_minutes'] for row in history]
        steps_list = [row['step_count'] for row in history]
        backspaces_list = [row['backspace_count'] or 0 for row in history]

        screen_m, screen_s = float(np.mean(screens)), max(float(np.std(screens)), 1.0)
        unlock_m, unlock_s = float(np.mean(unlocks_list)), max(float(np.std(unlocks_list)), 1.0)
        night_m, night_s = float(np.mean(nights)), max(float(np.std(nights)), 1.0)
        step_m, step_s = float(np.mean(steps_list)), max(float(np.std(steps_list)), 1.0)
        backspace_m, backspace_s = float(np.mean(backspaces_list)), max(float(np.std(backspaces_list)), 1.0)

    z_screen = (screen - screen_m) / screen_s
    z_unlocks = (unlocks - unlock_m) / unlock_s
    z_night = (night - night_m) / night_s
    z_steps = (step_m - steps) / step_s
    z_backspace = (backspaces - backspace_m) / backspace_s

    composite_z = (0.25 * z_screen) + (0.20 * z_unlocks) + (0.20 * z_night) + (0.15 * z_steps) + (0.20 * z_backspace)
    stress_score = int(100 / (1 + np.exp(-composite_z)))
    return stress_score

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "online", "service": "Passive Stress Biomarker API"}), 200

@app.route('/api/v1/telemetry', methods=['POST'])
def receive_telemetry():
    try:
        data = request.get_json()
        device_id = data.get('device_id', 'unknown_device')
        screen = data.get('screen_on_time_minutes', 0)
        unlocks = data.get('unlock_count', 0)
        night = data.get('night_usage_minutes', 0)
        steps = data.get('step_count', 0)

        keystrokes = data.get('keystroke_biomarkers', {})
        backspaces = keystrokes.get('backspace_count', 0)
        typing_speed = keystrokes.get('avg_typing_speed_ms', 0)

        score = calculate_stress_index(device_id, screen, unlocks, night, steps, backspaces)
        status, advice = generate_ai_counselor_advice(score, screen, night, steps, backspaces)

        conn = get_db_connection()
        conn.execute(
            '''INSERT INTO daily_telemetry 
               (device_id, screen_on_time_minutes, unlock_count, night_usage_minutes, step_count, backspace_count, avg_typing_speed_ms, stress_score) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (device_id, screen, unlocks, night, steps, backspaces, typing_speed, score)
        )
        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "stress_score": score,
            "stress_level": status,
            "ai_advice": advice
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/v1/history/<device_id>', methods=['GET'])
def get_history(device_id):
    conn = get_db_connection()
    rows = conn.execute(
        '''SELECT stress_score, screen_on_time_minutes, unlock_count, step_count, backspace_count, timestamp 
           FROM daily_telemetry WHERE device_id = ? ORDER BY id DESC LIMIT 7''',
        (device_id,)
    ).fetchall()
    conn.close()
    return jsonify({"history": [dict(row) for row in rows]}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)