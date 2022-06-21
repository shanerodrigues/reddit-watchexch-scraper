import praw
from psaw import PushshiftAPI
import datetime
from string import Template
import pystache
import schedule
import time
import json
import smtplib
import requests
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import pystache
from pathlib import Path
import ssl
import os
# from os import environ
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

r = praw.Reddit(
    client_id=os.getenv('REDDIT_CLIENT_ID'),
    client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
    user_agent="PyBot",
)

subreddit = r.subreddit("watchexchange")

def get_settings(f_settings: Path = Path() / "settings.json") -> dict:
    """Read in the Gmail username/password to use"""
    print("Getting Gmail credentials")
    with f_settings.open() as settings_json:
        settings = json.load(settings_json)

    return settings

def send_email_handler(query, address, listings, count) -> None:
    """General handler function for sending the email"""
    print("Starting to send email")
    credentials = get_settings()

    # Set up gmail info, modifying for our "real" gmail account
    gmail_username = credentials["gmail_user"]
    gmail_password = credentials["gmail_pass"]
    port = 465
    gmail_smtp_url = "smtp.gmail.com"

    # Create a secure SSL context so you know your email is encrypted on the way to the server
    context = ssl.create_default_context()

    # read in the email template, remember to use the compiled HTML version!
    email_template = (Path() / "email_template" / "email_template.html").read_text()

    # Get emails from the settings.json
    receiver_email = "example@hotmail.com"
    sender_email = "example@gmail.com"

    # Creating the email
    message = MIMEMultipart("mixed")
    message["Subject"] = "New " + f"{query}" + " watch listings"
    message["From"] = "WatchScraper Bot"
    message["To"] = address
    final_email_html = ""

    html = """\
            <html>
            <body>
                <p>Hi, we found $number listings for your query today </p>
            </body>
            </html>
            """
    s = Template(html).substitute({"number": count})
    final_email_html += s
    if len(listings) < 1:
        message["Subject"] = "No listings for your query " + f"{query}"
    else:
        for item in listings:
            # Pass in values for the template using a dictionary
            newDescription = item["description"][0:400] + "..."
            template_params = {
                "title": item["title"],
                "watch_picture": item["watch_picture"],
                "transactions": item["transactions_flair"],
                "time-posted": item["time_posted"],
                "author": item["author"],
                "price-range": item["price_flair"],
                "preview": "New " + f"{query}" + " watch listings inside!",
                "description": newDescription,
                "URL": item["URL"],
            }
            # Now adjust the pystache dictionary to handle both variables
            final_email_html += pystache.render(email_template, template_params)

    part = MIMEText(final_email_html, "html")
    # part1 = MIMEText("Hello we found 4 listings!", "html")
    # message.attach(part1)
    message.attach(part)

    # Send the same test email as before, but through gmail to a "real" gmail account!
    with smtplib.SMTP_SSL(gmail_smtp_url, port, context=context) as gmail_server:
        gmail_server.login(gmail_username, gmail_password)
        gmail_server.sendmail(gmail_username, address, message.as_string())
        
def send_email_mailgun(query, address, listings, count):
    # read in the email template, remember to use the compiled HTML version!
    email_template = (Path() / "email_template" / "email_template.html").read_text()
    
    MAILGUN_APIKEY=os.getenv('MAILGUN_APIKEY')
    MAILGUN_DOMAIN=os.getenv('MAILGUN_DOMAIN')

    final_email_html = ""
    if len(listings) < 1:
        res = requests.post(
        f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
        auth=("api", MAILGUN_APIKEY),
        data={"from": f"WatchExch Scraper <digest@{MAILGUN_DOMAIN}>",
              "to": [address],
              "subject": f"No listings for {query} today",
              "text": f'No listings for your query: {query}',
              "html": f'No listings for your query: {query}' })
        if res.ok:
            print(f"Sent digest email to {address}")
        else:
            print("Failed to send digest email.")
    else:
        html = """\
            <html>
            <body>
                <p>Hi, we found $number listings for your query today </p>
            </body>
            </html>
            """
        s = Template(html).substitute({"number": count})
        final_email_html += s
        for item in listings:          
            # Pass in values for the template using a dictionary
            newDescription = item["description"][0:400] + "..."
            template_params = {
                "title": item["title"],
                "watch_picture": item["watch_picture"],
                "transactions": item["transactions_flair"],
                "time-posted": item["time_posted"],
                "author": item["author"],
                "price-range": item["price_flair"],
                "preview": "New " + f"{query}" + " watch listings inside!",
                "description": newDescription,
                "URL": item["URL"],
            }
            # Now adjust the pystache dictionary to handle both variables
            temp = pystache.render(email_template, template_params)
            final_email_html += temp
             # Send email
        res = requests.post(
            f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
            auth=("api", MAILGUN_APIKEY),
            data={"from": f"WatchExch Scraper <digest@{MAILGUN_DOMAIN}>",
                "to": [address],
                "subject": f"{count} listings for {query} today",
                "html": final_email_html})

        if res.ok:
            print(f"Sent digest email to {address}")
        else:
            print("Failed to send digest email.")
        
def findListings(query):
    listings=[]
    count = 0
    for submission in r.subreddit("watchexchange").search(query, time_filter="day", sort="new"):
        if submission.link_flair_text != "Sold":
            opComment = ""
            length = 0
            for comment in submission.comments:
                if comment.author == submission.author and length != 1:
                    opComment = comment.body
                    length = length + 1
            # Getting submission time+date
            date_time = datetime.datetime.fromtimestamp(submission.created_utc)
            # Getting clickable URL
            theUrl = "https://www.reddit.com" + submission.permalink
            print("Title: ", submission.title)
            print("Author: ", submission.author)
            count = count + 1
            # print("Number of author's transactions: ", submission.author_flair_text)
            # print("Price flair: ", submission.link_flair_text)
            # print("Time posted: ", date_time)
            # # encode utf-8 to prevent unicodeencodeerror opComment.encode("utf-8") .encode("ASCII", "ignore")
            # print("Description: ", opComment.encode("ASCII", "ignore"))
            # # print("Transactions: ", submission.author.author_flair_text)
            # print("URL: ", "https://www.reddit.com" + submission.permalink)
            # print("\n")

            # Getting image
            listingImage = ""
            subm = r.submission(url=theUrl)
            if hasattr(subm, "media_metadata"):
                image_dict = subm.media_metadata

                for image_item in image_dict.values():
                    largest_image = image_item["s"]
                    image_url = largest_image["u"]
                    listingImage = image_url
                    break
            if hasattr(subm, "preview") == True:
                if "images" in submission.preview:
                    # print("Submission has an image preview")
                    preview_image_link = submission.preview["images"][0]["source"]["url"]
                    listingImage = preview_image_link

            keys = [
                "id",
                "title",
                "author",
                "transactions_flair",
                "price_flair",
                "time_posted",
                "description",
                "URL",
                "watch_picture",
            ]
            values = [
                submission.id,
                str(submission.title),
                str(submission.author),
                str(submission.author_flair_text),
                str(submission.link_flair_text),
                str(date_time),
                str(opComment),
                str(theUrl),
                str(listingImage),
            ]

            listings.append(dict(zip(keys, values)))
    return count, listings

def doJob(query, address):
    count, listings = findListings(query)
    send_email_mailgun(query, address, listings, count)