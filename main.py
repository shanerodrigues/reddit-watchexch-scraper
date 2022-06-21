import random
from celery import Celery
from flask import Flask, request, render_template, session, flash, redirect, url_for
from functools import wraps
import os, pymongo, time

from dateutil import parser

import lib.scraper as scraper
import lib.tasks as tasks
from lib.db import connect_to_db

app = Flask(__name__)

SECRET_KEY= os.getenv("SECRET_KEY")

app.config['SECRET_KEY'] = SECRET_KEY

db = connect_to_db()

# Authentication decorator
def authenticated(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):

        if "email" not in session:
            flash("Permission denied.", "warning")
            return redirect(url_for("index"))

        return f(*args, **kwargs)

    return decorated_function

def context():
    email = session["email"] if "email" in session else None

    cursor = db.subscriptions.find({ "email": email })
    subscriptions = [subscription for subscription in cursor]
    
    schedule_cursor = db.schedules.find({"email": email})
    schedules = [schedule for schedule in schedule_cursor]

    return {
        "user_email": email,
        "user_subscriptions": subscriptions,
        "user_schedule": schedules
    }
    

@app.route("/confirm-login/<login_id>")
def confirm_login(login_id):
    login = db.user_sessions.find_one({"login_id": login_id})

    if login:
        session["email"] = login["email"]
        db.user_sessions.delete_one({"login_id": login_id}) # prevent reuse
    else:
        flash("Invalid or expired login link.")

    return redirect(url_for("index"))

# Login
@app.route("/login", methods=['POST'])
def login():
    email = request.form['email']
    tasks.send_login_email.delay(email)
    flash("Check your email for a magic login link!")

    return redirect(url_for("index"))

# Subscriptions
@authenticated
@app.route("/subscribe", methods=['POST'])
def subscribe(): # new feed
    search_query = request.form["search_query"]
    query_url = f"https://www.reddit.com/r/Watchexchange/search/?q={search_query}&restrict_sr=1&sort=new"

    # Get feed title
    time.sleep(1) 
    
    # Add subscription to Mongodb
    try:
        db.subscriptions.insert_one({"email": session["email"], "url": query_url, "title": search_query})
    except pymongo.errors.DuplicateKeyError:
        flash("You're already subscribed to that feed.")
        return redirect(url_for("index"))
    except Exception:
        flash("An unknown error occured.")
        return redirect(url_for("index"))

    # Create unique index if it doesn't exist
    db.subscriptions.create_index([("email", 1), ("url", 1)], unique=True)

    flash("Feed added!")
    return redirect(url_for("index"))

@authenticated
@app.route("/unsubscribe", methods=['POST'])
def unsubscribe(): # remove feed

    query_url = request.form["query_url"]
    deleted = db.subscriptions.delete_one({"email": session["email"], "url": query_url})

    flash("Unsubscribed!")
    return redirect(url_for("index"))

@app.route('/logout')
def logout():
    session.pop('email',None)
    return redirect(url_for('index'))

# Digest
@authenticated
@app.route("/send-digest", methods=['POST'])
def send_digest():

    tasks.send_digest_email.delay(session["email"])

    flash("Digest email sent! Check your inbox.")
    return redirect(url_for("index"))

@authenticated
@app.route("/schedule-digest", methods=['POST'])
def schedule_digest():

    # Get time from form
    try:
        hour, minute = request.form["digest_time"].split(":")
    except:
        flash("Error: need to provide a time to schedule.")
        return redirect(url_for("index"))
    # tasks.setup_periodic_tasks(hour=hour, minute=minute, email=session['email'])
    tasks.schedule_digest(session["email"], int(hour), int(minute))
    
    # ADDING TO MONGO
    if (db.schedules.count_documents({ "email" : session['email']}) > 0):
        filter= { "email": session['email']}
        newTime = { "$set" : { 'time_scheduled': f'{hour}:{minute}'}}
        db.schedules.update_one(filter,newTime)
    else:
        try:
            db.schedules.insert_one({"email": session["email"], "time_scheduled": f'{hour}:{minute}'})
        except Exception:
            flash("An unknown error occured.")
            return redirect(url_for("index"))
    # Create unique index if it doesn't exist
    db.subscriptions.create_index([("email", 1), ("url", 1)], unique=True)
    
    flash("Email schedule added!")
    ''' 

    '''
    flash(f"Your digest will be sent daily at {hour}:{minute} UTC")
    return redirect(url_for("index"))

@authenticated
@app.route("/remove-schedule", methods=['POST'])
def remove_schedule():
    if (db.schedules.count_documents({ "email" : session['email']}) > 0):
        deleted = db.schedules.delete_one({"email": session["email"]})
        tasks.remove_task(session["email"])
        flash(f'Your scheduled email is removed')
    else:
        flash(f'Error no schedule to remove')
    
    # tasks.remove_task(session["email"])
    # flash("Schedule removed!")
    return redirect(url_for("index"))
    
# Routes
@app.route("/")
def index():
    return render_template("index.html", **context())