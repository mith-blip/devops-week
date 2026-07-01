from flask import Flask, jsonify
import os
import psycopg2
import redis

app = Flask(__name__)

# Read connection info from environment variables — NOT hardcoded.
# This is the 12-factor principle: config comes from the environment.
DB_HOST = os.environ.get("DB_HOST", "db")
DB_NAME = os.environ.get("DB_NAME", "appdb")
DB_USER = os.environ.get("DB_USER", "appuser")
DB_PASS = os.environ.get("DB_PASS", "secret")
REDIS_HOST = os.environ.get("REDIS_HOST", "cache")

@app.route("/")
def home():
    return jsonify(message="Hello from my DevOps app!",
                   hostname=os.environ.get("HOSTNAME", "unknown"))

@app.route("/health")
def health():
    return jsonify(status="healthy"), 200

@app.route("/db")
def db_check():
    # Connect to Postgres using the service name 'db' as the host
    conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME,
                            user=DB_USER, password=DB_PASS)
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()[0]
    cur.close()
    conn.close()
    return jsonify(database="connected", version=version)

@app.route("/visits")
def visits():
    # Connect to Redis using the service name 'cache' as the host
    r = redis.Redis(host=REDIS_HOST, port=6379)
    count = r.incr("visits")  # atomically increment a counter
    return jsonify(visits=count)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)