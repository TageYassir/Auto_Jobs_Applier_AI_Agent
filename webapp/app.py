import os
from pathlib import Path
from datetime import datetime
import threading
from flask import Flask, render_template, request, jsonify, current_app
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev')
app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

from models import db, Run, ApplicationLog, Configuration, ResumeContent
db.init_app(app)

# Import bot runner after db to avoid circular import
from bot_runner import BotThread

bot_thread = None
bot_lock = threading.Lock()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def status():
    running = bot_thread is not None and bot_thread.is_alive()
    return jsonify({'running': running})

@app.route('/api/stats')
def stats():
    total_success = ApplicationLog.query.filter_by(status='success').count()
    total_failed = ApplicationLog.query.filter_by(status='failed').count()
    total_skipped = ApplicationLog.query.filter_by(status='skipped').count()
    last_run = Run.query.order_by(Run.id.desc()).first()
    return jsonify({
        'applied': total_success,
        'failed': total_failed,
        'skipped': total_skipped,
        'last_run_status': last_run.status if last_run else None
    })

@app.route('/api/logs')
def logs():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    logs_q = ApplicationLog.query.order_by(ApplicationLog.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    data = [{
        'job_title': l.job_title,
        'company': l.company,
        'status': l.status,
        'reason': l.reason,
        'timestamp': l.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    } for l in logs_q.items]
    return jsonify({'logs': data, 'has_next': logs_q.has_next})

@app.route('/api/start', methods=['POST'])
def start_bot():
    global bot_thread
    with bot_lock:
        if bot_thread and bot_thread.is_alive():
            return jsonify({'error': 'Bot is already running'}), 409
        bot_thread = BotThread(app)
        bot_thread.start()
    return jsonify({'message': 'Bot started'})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    global bot_thread
    with bot_lock:
        if not bot_thread or not bot_thread.is_alive():
            return jsonify({'error': 'Bot is not running'}), 409
        bot_thread.stop()
    return jsonify({'message': 'Stop signal sent'})

@app.route('/api/config', methods=['GET', 'POST'])
def config():
    cfg = db.session.get(Configuration, 1)
    if request.method == 'GET':
        if not cfg:
            return jsonify({})
        return jsonify({
            'manual_position': cfg.manual_position,
            'countries': cfg.countries,
            'contract_types': cfg.contract_types,
            'experience_level': cfg.experience_level,
            'remote': cfg.remote,
            'hybrid': cfg.hybrid,
            'onsite': cfg.onsite,
            'distance': cfg.distance,
            'date_filter': cfg.date_filter,
            'apply_once_at_company': cfg.apply_once_at_company,
            'company_blacklist': cfg.company_blacklist,
            'title_blacklist': cfg.title_blacklist,
            'location_blacklist': cfg.location_blacklist,
            'cv_path': cfg.cv_path,
        })
    # POST
    data = request.get_json()
    if not cfg:
        cfg = Configuration(id=1)
        db.session.add(cfg)
    for field in ['manual_position','countries','contract_types','experience_level',
                  'remote','hybrid','onsite','distance','date_filter',
                  'apply_once_at_company','company_blacklist','title_blacklist',
                  'location_blacklist', 'cv_path']:
        if field in data:
            setattr(cfg, field, data[field])
    db.session.commit()
    return jsonify({'message': 'Configuration updated'})

@app.route('/api/resume', methods=['GET', 'POST'])
def resume():
    res = db.session.get(ResumeContent, 1)
    if request.method == 'GET':
        return jsonify({'content': res.plain_text_yaml if res else ''})
    content = request.get_json().get('content', '')
    if not res:
        res = ResumeContent(id=1, plain_text_yaml=content)
        db.session.add(res)
    else:
        res.plain_text_yaml = content
    db.session.commit()
    return jsonify({'message': 'Resume updated'})

@app.route('/api/upload_cv', methods=['POST'])
def upload_cv():
    file = request.files.get('cv_file')
    if not file:
        return jsonify({'error': 'No file'}), 400
    upload_dir = Path.cwd() / 'data_folder' / 'output'
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / 'uploaded_cv.pdf'
    file.save(dest)
    # Save path to configuration
    cfg = db.session.get(Configuration, 1)
    if not cfg:
        cfg = Configuration(id=1)
        db.session.add(cfg)
    cfg.cv_path = str(dest.resolve())
    db.session.commit()
    return jsonify({'message': 'CV uploaded', 'path': cfg.cv_path})

@app.route('/api/remove_cv', methods=['POST'])
def remove_cv():
    cfg = db.session.get(Configuration, 1)
    if cfg:
        cfg.cv_path = None
        db.session.commit()
    return jsonify({'message': 'CV removed'})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=False, host='0.0.0.0', port=5000)