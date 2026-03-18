"""
locustfile.py
Locust load generator for the LLM load balancer.

Usage:
    locust -f locustfile.py --host http://localhost:9000 --headless \
           -u 20 -r 2 --run-time 120s \
           --csv results/locust_stats

Install: pip install locust
"""

import random
from locust import HttpUser, task, between

# Sample prompts to simulate realistic LLM traffic
PROMPTS = [
    "What is the capital of France?",
    "Explain quantum computing in simple terms.",
    "Write a short poem about the ocean.",
    "What are the main causes of World War I?",
    "How does photosynthesis work?",
    "Give me a recipe for chocolate chip cookies.",
    "What is machine learning?",
    "Describe the water cycle.",
    "Who was Albert Einstein?",
    "What is the speed of light?",
    "Explain the difference between RAM and ROM.",
    "What is the Pythagorean theorem?",
    "How do airplanes fly?",
    "What is climate change?",
    "Explain how the internet works.",
]


class LLMUser(HttpUser):
    """Simulates a user sending inference requests to the load balancer."""
    wait_time = between(1, 3)  # Wait 1-3 seconds between requests

    @task(3)
    def short_query(self):
        """Short, fast queries — high frequency."""
        prompt = random.choice(PROMPTS[:5])
        self.client.post(
            "/infer",
            json={"prompt": prompt, "max_tokens": 50},
            name="/infer [short]"
        )

    @task(2)
    def medium_query(self):
        """Medium queries."""
        prompt = random.choice(PROMPTS[5:10])
        self.client.post(
            "/infer",
            json={"prompt": prompt, "max_tokens": 100},
            name="/infer [medium]"
        )

    @task(1)
    def long_query(self):
        """Long queries — low frequency, heavy load."""
        prompt = random.choice(PROMPTS[10:])
        self.client.post(
            "/infer",
            json={"prompt": prompt, "max_tokens": 200},
            name="/infer [long]"
        )

    @task(1)
    def health_check(self):
        """Occasional health checks."""
        self.client.get("/health", name="/health")
