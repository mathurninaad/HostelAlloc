import os
from mongoengine import connect

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017/hostelalloc")

if MONGO_URL.startswith("mongomock"):
    import mongomock
    connect("hostelalloc_test", host="mongodb://localhost", mongo_client_class=mongomock.MongoClient)
else:
    connect(host=MONGO_URL)
