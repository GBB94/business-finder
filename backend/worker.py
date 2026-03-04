"""RQ worker entrypoint for IdeaScope background jobs."""

import redis
from rq import Worker, Queue, Connection

from app.config import settings


def main():
    conn = redis.from_url(settings.REDIS_URL)
    with Connection(conn):
        worker = Worker([Queue("default")])
        worker.work()


if __name__ == "__main__":
    main()
