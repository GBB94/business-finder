"""RQ worker entrypoint for IdeaScope background jobs."""

import redis
from rq import Worker, Queue

from app.config import settings


def main():
    conn = redis.from_url(settings.REDIS_URL)
    queues = [
        Queue("agent_tasks", connection=conn),
        Queue("default", connection=conn),
        # LaunchPad dedicated queues (consumed by split workers in production,
        # but this generic worker handles them all in dev)
        Queue("provision", connection=conn),
        Queue("engineering", connection=conn),
        Queue("ceo", connection=conn),
        Queue("marketing", connection=conn),
        Queue("support", connection=conn),
    ]
    worker = Worker(queues, connection=conn)
    worker.work()


if __name__ == "__main__":
    main()
