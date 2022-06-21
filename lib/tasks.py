import json
import requests, os
from os import environ

import random, string
from celery import Celery 
from celery.schedules import crontab
from pathlib import Path
import lib.scraper as scraper 
from lib.db import connect_to_db 
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

from redisbeat.scheduler import RedisScheduler
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

MAILGUN_APIKEY=os.getenv('MAILGUN_APIKEY')
MAILGUN_DOMAIN=os.getenv('MAILGUN_DOMAIN')

REPL_URL = f"http://127.0.0.1:5000"

CELERY_BROKER_URL = "redis://127.0.0.1:6379/0"
CELERY_BACKEND_URL = "redis://127.0.0.1:6379/0"

os.environ.setdefault('FORKED_BY_MULTIPROCESSING', '1')
celery = Celery("tasks", broker=CELERY_BROKER_URL, backed=CELERY_BACKEND_URL, CELERY_REDIS_SCHEDULER_URL='redis://127.0.0.1:6379', beat_max_loop_interval=60)

celery.conf.update(
    timezone='UTC',
    enable_utc=True,
)


scheduler = RedisScheduler(app=celery)
celery.autodiscover_tasks()

def generate_login_id():
    return ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(30))

def get_settings(f_settings: Path = Path() / "settings.json") -> dict:
    """Read in the Gmail username/password to use"""
    print("Getting Mailgun credentials")
    with f_settings.open() as settings_json:
        settings = json.load(settings_json)

    return settings

@celery.task
def send_test_email(to_address):
    email_template = (Path() / "email_template" / "email_template.html").read_text()
    template_params = {
                "title": "title",
                "watch_picture": "watch_picture",
                "transactions": "transactions",
                "time-posted": "time",
                "author": 'author',
                "price-range": "price",
                "preview": "New " + "5" + " watch listings inside!",
                "description": "desc",
                "URL": "URL",
            }
    html = """\
            <html>
            <body>
                <h1>Hi, we found $number listings for your query today </h1>
            </body>
            </html>
            """
    
    s = string.Template(email_template).substitute(template_params)
    s += string.Template(email_template).substitute(template_params)
    res = requests.post(
        f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
        auth=("api", MAILGUN_APIKEY),
        data={"from": f"News Digest <digest@{MAILGUN_DOMAIN}>",
              "to": [to_address],
              "subject": "Testing Mailgun",
              "html": s})

    print(res)


def send_email_sendinblue(to_address):
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = os.getenv('SENDINBLUE_APIKEY')
    
    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
    subject = "from the Python SDK!"
    sender = {"name":"Sendinblue","email":"Scraper@sendinblue.com"}
    replyTo = {"name":"Sendinblue","email":"Scraper@sendinblue.com"}
    html_content = "<html><body><h1>This is my first transactional email </h1></body></html>"
    to = [{"email":"demo@demo.com","name":"Jane Doe"}]
    # params = {"parameter":"My param value","subject":"New Subject"}
    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(to=to, reply_to=replyTo, html_content=html_content, sender=sender, subject=subject)

    try:
        api_response = api_instance.send_transac_email(send_smtp_email)
        print(api_response)
    except ApiException as e:
        print("Exception when calling SMTPApi->send_transac_email: %s\n" % e)

@celery.task
def send_login_email(to_address):
    # Generate ID
    login_id = generate_login_id()

    # Set up email
    login_url = f"{REPL_URL}/confirm-login/{login_id}"

    text = f"""
    Click this link to log in:
    
    {login_url}
    """

    html = f"""
    <p>Click this link to log in:</p>
    
    <p><a href={login_url}>{login_url}</a></p>
    """

    # Send email
    res = requests.post(
        f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
        auth=("api", MAILGUN_APIKEY),
        data={"from": f"News Digest <digest@{MAILGUN_DOMAIN}>",
              "to": [to_address],
              "subject": "News Digest Login Link",
              "text": text,
              "html": html })

    # Add to user_sessions collection if email sent successfully
    if res.ok:
        db = connect_to_db()
        db.user_sessions.insert_one({"login_id": login_id, "email": to_address})

        print(f"Sent login email to {to_address}")
    else:
        print("Failed to send login email.")


def schedule_digest(email, hour, minute):
    
    # Remove task if exists
    scheduler.remove('digest-'+email)
    
    # add new task
    scheduler.add(**{
        "name": "digest-" + email,
        "task": "lib.tasks.send_digest_email",
        "kwargs": {"to_address": email },
        "schedule": crontab(minute=minute, hour=hour),
    })



# @celery.task
def remove_task(email):
     # Remove task if exists
    result=scheduler.remove('digest-'+email)
    print("rem result: ", result)
        
@celery.task
def send_digest_email(to_address):

    # Get subscriptions from Mongodb
    db = connect_to_db()
    cursor = db.subscriptions.find({"email": to_address})
    subscriptions = [subscription for subscription in cursor]
    
    items = list(subscriptions)

    # For each query, find listings and send email
    for item in items:
        scraper.doJob(item["title"], to_address)
    
# Debug email 
# send_test_email("email@gmail.com")
# send_email_sendinblue("email@hotmail.com")