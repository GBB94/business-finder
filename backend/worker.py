"""RQ worker entrypoint for IdeaScope background jobs."""

import redis
from rq import Worker, Queue

from app.config import settings


def main():
    conn = redis.from_url(settings.REDIS_URL)
    worker = Worker([Queue("default", connection=conn)], connection=conn)
    worker.work()


if __name__ == "__main__":
    main()
