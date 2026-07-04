from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.mysql import JSON, MEDIUMTEXT
from datetime import datetime

db = SQLAlchemy()

class Run(db.Model):
    __tablename__ = 'run'
    id = db.Column(db.Integer, primary_key=True)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime)
    status = db.Column(db.Enum('running','stopped','finished','error'), nullable=False)
    notes = db.Column(db.Text)

class ApplicationLog(db.Model):
    __tablename__ = 'application_log'
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey('run.id'), nullable=False)
    job_title = db.Column(db.String(255))
    company = db.Column(db.String(255))
    link = db.Column(db.Text)
    location = db.Column(db.String(255))
    status = db.Column(db.Enum('applied','success','failed','skipped'), nullable=False)
    reason = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    run = db.relationship('Run', backref='logs')

class Configuration(db.Model):
    __tablename__ = 'configuration'
    id = db.Column(db.Integer, primary_key=True, default=1)
    manual_position = db.Column(db.Text)
    countries = db.Column(db.Text)
    contract_types = db.Column(JSON)
    experience_level = db.Column(JSON)
    remote = db.Column(db.Boolean, default=True)
    hybrid = db.Column(db.Boolean, default=True)
    onsite = db.Column(db.Boolean, default=True)
    distance = db.Column(db.Integer, default=100)
    date_filter = db.Column(db.Enum('all_time','month','week','24_hours'), default='24_hours')
    apply_once_at_company = db.Column(db.Boolean, default=True)
    company_blacklist = db.Column(db.Text)
    title_blacklist = db.Column(db.Text)
    location_blacklist = db.Column(db.Text)
    cv_path = db.Column(db.Text)   # <-- new field for uploaded CV

class ResumeContent(db.Model):
    __tablename__ = 'resume_content'
    id = db.Column(db.Integer, primary_key=True, default=1)
    plain_text_yaml = db.Column(MEDIUMTEXT, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)