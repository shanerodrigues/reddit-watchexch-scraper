import pymongo
from os import environ

def connect_to_db():
    client = pymongo.MongoClient(environ.get('MONGO_URL'))
    return client.newsletter