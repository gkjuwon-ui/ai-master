#!/usr/bin/env python3
"""
generate_dataset.py — Generate JSONL training dataset for Ogenti

Creates a diverse set of tasks across all 12 categories organized by
curriculum difficulty. Output: data/train.jsonl + data/eval.jsonl

Run: python scripts/generate_dataset.py
"""

import json
import random
from pathlib import Path

# ─── Task Templates ─────────────────────────────────────────────

TASKS = []

def add(category, instruction, reference, difficulty=0.5, num_agents=2, **kw):
    TASKS.append({
        "task_id": f"{category}_{len(TASKS):04d}",
        "category": category,
        "instruction": instruction,
        "reference": reference,
        "difficulty": difficulty,
        "num_agents": num_agents,
        "metadata": kw,
    })


# ══════════════════════════════════════════════════════════════
#  Phase 0 — Warmup Tasks (summarize, translate, qa)
# ══════════════════════════════════════════════════════════════

# --- Summarize ---
summarize_pairs = [
    ("Summarize: Machine learning is a branch of artificial intelligence that uses algorithms to learn patterns from data and make predictions without being explicitly programmed.",
     "ML uses algorithms to learn from data and make predictions automatically."),
    ("Summarize: The Python programming language was created by Guido van Rossum and released in 1991. It emphasizes code readability with significant whitespace and supports multiple programming paradigms.",
     "Python, created by van Rossum in 1991, emphasizes readability and supports multiple paradigms."),
    ("Summarize: Neural networks are computing systems inspired by biological neural networks. They consist of interconnected nodes organized in layers that process information using connectionist approaches to computation.",
     "Neural networks are bio-inspired layered computing systems for information processing."),
    ("Summarize: Docker is a platform for developing, shipping, and running applications inside lightweight containers. It packages software with all dependencies so it runs consistently across environments.",
     "Docker packages applications in containers for consistent cross-environment deployment."),
    ("Summarize: Git is a distributed version control system that tracks changes in source code during software development. It was created by Linus Torvalds in 2005 for Linux kernel development.",
     "Git is a distributed VCS created by Torvalds in 2005 for tracking code changes."),
    ("Summarize: The transformer architecture uses self-attention mechanisms to process sequential data in parallel. Introduced in 2017, it revolutionized NLP and became the foundation for models like GPT and BERT.",
     "Transformers use self-attention for parallel sequential processing, enabling GPT and BERT."),
    ("Summarize: Kubernetes is an open-source container orchestration system that automates deploying, scaling, and managing containerized applications across clusters of machines.",
     "Kubernetes automates container deployment, scaling and management across server clusters."),
    ("Summarize: REST APIs use standard HTTP methods to enable communication between client and server applications. They follow principles of statelessness and resource-based URLs.",
     "REST APIs use HTTP methods for stateless client-server communication via resource URLs."),
    ("Summarize: Reinforcement learning is an area of machine learning where agents learn to make decisions by taking actions in an environment to maximize cumulative reward signals.",
     "RL trains agents to make sequential decisions that maximize cumulative rewards."),
    ("Summarize: PostgreSQL is an advanced open-source relational database system that supports both SQL and JSON querying, offering ACID compliance, extensibility, and strong data integrity.",
     "PostgreSQL is an open-source relational DB with SQL/JSON support and ACID compliance."),
    ("Summarize: WebAssembly is a binary instruction format for a stack-based virtual machine designed to be a portable compilation target for high-level languages, enabling deployment on the web.",
     "WebAssembly is a portable binary format allowing high-level languages to run on the web."),
    ("Summarize: The CAP theorem states that a distributed system cannot simultaneously provide consistency, availability, and partition tolerance. You can only guarantee two of the three properties.",
     "CAP theorem: distributed systems can guarantee only 2 of consistency, availability, and partition tolerance."),
    ("Summarize: Federated learning is a machine learning approach where models are trained across decentralized devices holding local data, without transferring raw data to a central server.",
     "Federated learning trains models on decentralized devices without sharing raw data."),
    ("Summarize: MapReduce is a programming model for processing large data sets in parallel across a distributed cluster. It consists of a Map step that filters data and a Reduce step that aggregates results.",
     "MapReduce processes big data in parallel using Map (filter) and Reduce (aggregate) steps."),
    ("Summarize: GraphQL is a query language for APIs that allows clients to request exactly the data they need. Unlike REST, it provides a single endpoint and uses a type system to describe data.",
     "GraphQL lets clients query exactly the data they need through a single typed endpoint."),
]
for instr, ref in summarize_pairs:
    add("summarize", instr, ref, difficulty=0.3)

# --- Translate ---
translate_pairs = [
    ("Translate to formal English: hey can u help me fix this bug its driving me crazy lol",
     "Could you assist me in resolving this defect? It has been quite frustrating."),
    ("Translate this technical text to simple terms: The system uses a B+ tree index with a fanout of 256 for logarithmic query complexity.",
     "The system organizes data in a tree structure that makes searching very fast."),
    ("Translate to Korean: The weather is nice today and I plan to go for a walk in the park.",
     "오늘 날씨가 좋아서 공원에서 산책할 계획입니다."),
    ("Translate to simple English: Photosynthesis is the biochemical process by which chloroplasts convert photonic energy into adenosine triphosphate via the Calvin cycle.",
     "Plants use sunlight to make food energy through a chemical process in their cells."),
    ("Translate code comment to English: # 이 함수는 데이터를 정제하고 중복을 제거합니다",
     "This function cleans the data and removes duplicates."),
    ("Translate to professional email tone: yo we need to push the deadline back a week, the client changed requirements again smh",
     "I'm writing to request a one-week extension on our deadline, as the client has revised their requirements."),
    ("Rewrite in active voice: The report was written by the team. The data was analyzed using Python. The results were presented to the board.",
     "The team wrote the report. They analyzed the data using Python. They presented the results to the board."),
    ("Translate to technical specification: Make a button that turns green when you click it and shows a number that goes up each time.",
     "Implement a button component with onClick handler that toggles background-color to #00FF00 and increments a counter state displayed as text content."),
    ("Translate to layman's terms: The CRISPR-Cas9 system enables precise genomic editing by utilizing guide RNA to direct the Cas9 endonuclease to specific DNA loci for targeted double-strand breaks.",
     "CRISPR is a tool that lets scientists edit DNA precisely by cutting it at specific locations using a guided molecular scissors."),
    ("Translate to children's language: Gravity is the fundamental force of attraction between objects with mass. It keeps planets in orbit and causes objects to fall toward the ground.",
     "Gravity is the invisible pull that keeps us on the ground and makes the planets go around the sun. It's why things fall down!"),
]
for instr, ref in translate_pairs:
    add("translate", instr, ref, difficulty=0.4)

# --- QA ---
qa_pairs = [
    ("What is the capital of France?", "Paris"),
    ("What programming language is PyTorch primarily written in?", "Python and C++"),
    ("How many bits are in a byte?", "8"),
    ("Who created the Linux kernel?", "Linus Torvalds"),
    ("What does API stand for?", "Application Programming Interface"),
    ("What is the time complexity of binary search?", "O(log n)"),
    ("What port does HTTPS use by default?", "443"),
    ("What does GPU stand for?", "Graphics Processing Unit"),
    ("What year was Python 3 released?", "2008"),
    ("What is the default port for PostgreSQL?", "5432"),
    ("What does CRUD stand for?", "Create, Read, Update, Delete"),
    ("How many layers does the OSI model have?", "7"),
    ("What is the result of 2^10?", "1024"),
    ("What encoding does JSON use?", "UTF-8"),
    ("What does DNS stand for?", "Domain Name System"),
    ("What is the latest major version of HTTP?", "HTTP/3"),
    ("What hash function does Git use?", "SHA-1 (transitioning to SHA-256)"),
    ("What design pattern does React use?", "Component-based architecture with Virtual DOM"),
    ("What is the default branch name in Git?", "main (previously master)"),
    ("How many bytes in a kilobyte (binary)?", "1024"),
]
for instr, ref in qa_pairs:
    add("qa", instr, ref, difficulty=0.2)


# ══════════════════════════════════════════════════════════════
#  Phase 1 — Simple Tasks (+ code_review, data_analysis, instruction_following)
# ══════════════════════════════════════════════════════════════

# --- Code Review ---
code_review_pairs = [
    ("Review this code for bugs:\ndef divide(a, b):\n    return a / b",
     "Missing division by zero check. Add: if b == 0: raise ValueError('Division by zero')."),
    ("Review this code:\ndef get_user(users, id):\n    for u in users:\n        if u.id == id:\n            return u",
     "Missing return None for not-found case. Consider using dict for O(1) lookup instead of O(n) loop."),
    ("Find the bug:\ndata = [1, 2, 3]\nfor i in range(len(data)):\n    if data[i] % 2 == 0:\n        data.remove(data[i])",
     "Modifying list while iterating causes index shift. Use list comprehension: data = [x for x in data if x % 2 != 0]."),
    ("Review for security:\nquery = f\"SELECT * FROM users WHERE name = '{user_input}'\"",
     "SQL injection vulnerability. Use parameterized queries: cursor.execute('SELECT * FROM users WHERE name = ?', (user_input,))."),
    ("Review this async code:\nasync def fetch_all(urls):\n    results = []\n    for url in urls:\n        r = await fetch(url)\n        results.append(r)\n    return results",
     "Sequential awaits lose concurrency benefit. Use: await asyncio.gather(*[fetch(url) for url in urls])."),
    ("Review:\nclass Config:\n    DEBUG = True\n    API_KEY = 'sk-abc123'\n    DB_PASSWORD = 'admin123'",
     "Hardcoded secrets. Use environment variables: os.environ.get('API_KEY'). Never commit credentials."),
    ("Review this React component:\nfunction List({items}) {\n    return items.map(item => <div>{item.name}</div>)\n}",
     "Missing key prop in list rendering. Add: <div key={item.id}>{item.name}</div>. Also add null check for items."),
    ("Find the bug:\ndef fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)",
     "Exponential time complexity O(2^n). Add memoization with @functools.lru_cache or use iterative approach."),
    ("Review:\ntry:\n    result = process_data(input)\nexcept:\n    pass",
     "Bare except catches all exceptions including SystemExit and KeyboardInterrupt. Specify exception type. Never silently pass."),
    ("Review for performance:\ndef find_duplicates(lst):\n    duplicates = []\n    for i in range(len(lst)):\n        for j in range(i+1, len(lst)):\n            if lst[i] == lst[j] and lst[i] not in duplicates:\n                duplicates.append(lst[i])\n    return duplicates",
     "O(n³) complexity. Use Counter: from collections import Counter; return [x for x, c in Counter(lst).items() if c > 1]. O(n)."),
]
for instr, ref in code_review_pairs:
    add("code_review", instr, ref, difficulty=0.5)

# --- Data Analysis ---
data_analysis_pairs = [
    ("Analyze: Sales data shows Q1=$100K, Q2=$150K, Q3=$120K, Q4=$200K. What's the trend?",
     "Overall upward trend with Q3 dip. Q4 strongest at $200K. Total annual: $570K. Q2-Q3 decline suggests seasonal effect. Growth Q1→Q4: +100%."),
    ("Analyze: Server response times (ms): [45, 52, 48, 210, 47, 51, 890, 46, 49, 50]. Identify issues.",
     "Two outliers detected: 210ms and 890ms. Median: 49.5ms. Mean: 148.8ms (skewed by outliers). P95 likely >200ms. Investigate the spikes — possible GC pauses or network issues."),
    ("Given user retention: Day1=100%, Day7=40%, Day14=25%, Day30=15%, Day90=8%. Assess.",
     "Steep early drop (60% by Day 7) — typical for apps. D30 retention of 15% is below average (20%+ is good). Focus on Day 1-7 onboarding to improve curve."),
    ("Analyze error rates: Auth service: 0.1%, Payment: 2.3%, Search: 0.4%, Upload: 5.1%. Prioritize.",
     "Priority: Upload (5.1%) > Payment (2.3%) > Search (0.4%) > Auth (0.1%). Payment errors are revenue-critical despite lower rate. Upload service needs immediate investigation."),
    ("CPU usage over 24h: Night 15%, Morning 45%, Afternoon 80%, Evening 60%. Memory stable at 70%. Diagnose.",
     "CPU follows daily usage pattern. Afternoon peak at 80% approaching capacity. With memory at constant 70%, likely memory leak (should vary with load). Scale horizontally or optimize afternoon workload."),
]
for instr, ref in data_analysis_pairs:
    add("data_analysis", instr, ref, difficulty=0.6)

# --- Instruction Following ---
instruction_pairs = [
    ("List exactly 3 benefits of version control systems.",
     "1. Track changes history. 2. Enable team collaboration. 3. Provide backup and recovery."),
    ("Write a one-sentence definition of an API.",
     "An API is a set of protocols that allows different software applications to communicate with each other."),
    ("Explain the difference between stack and queue in exactly 2 sentences.",
     "A stack follows Last-In-First-Out (LIFO) — the last element added is the first removed. A queue follows First-In-First-Out (FIFO) — the first element added is the first removed."),
    ("Name 5 HTTP status codes and their meanings.",
     "200 OK, 301 Moved Permanently, 404 Not Found, 500 Internal Server Error, 403 Forbidden."),
    ("Write a Python one-liner that returns the sum of even numbers from 1 to 100.",
     "sum(x for x in range(1, 101) if x % 2 == 0)"),
    ("Explain microservices vs monolith in under 30 words.",
     "Microservices split an app into small independent services communicating via APIs. Monoliths package everything in one deployable unit. Microservices scale better but add complexity."),
    ("List the SOLID principles with one-word descriptions.",
     "Single Responsibility, Open-Closed, Liskov Substitution, Interface Segregation, Dependency Inversion."),
    ("Describe the purpose of a load balancer in one sentence.",
     "A load balancer distributes incoming network traffic across multiple servers to ensure no single server is overwhelmed."),
    ("What are the 4 pillars of OOP? List them.",
     "Encapsulation, Abstraction, Inheritance, Polymorphism."),
    ("Explain Big O notation in exactly 3 sentences.",
     "Big O describes the upper bound of an algorithm's time or space complexity. It shows how performance scales with input size. Common complexities are O(1), O(log n), O(n), O(n log n), O(n²)."),
]
for instr, ref in instruction_pairs:
    add("instruction_following", instr, ref, difficulty=0.3)


# ══════════════════════════════════════════════════════════════
#  Phase 2 — Complex Multi-hop Tasks
# ══════════════════════════════════════════════════════════════

# --- Chain Summarize ---
chain_pairs = [
    ("Read and process in stages: 'Kubernetes orchestrates containerized applications across clusters. It handles scaling, load balancing, and self-healing. Pods are the smallest deployable units.' First summarize, then simplify.",
     "Simple version: Kubernetes manages app containers across servers, automatically scaling them and fixing problems. The basic unit is called a Pod."),
    ("Multi-step: Analyze this error log, summarize the pattern, then suggest a fix: 'ERROR 15:01 DB timeout | ERROR 15:03 DB timeout | ERROR 15:05 DB connection refused | WARN 15:06 Pool exhausted'",
     "Pattern: Escalating database failures — timeouts leading to connection refusal and pool exhaustion. Fix: Increase connection pool size, add connection retry with backoff, check DB server health."),
    ("Chain task: Read the tech specs, extract key metrics, then generate a summary report: 'CPU: 8 cores @ 3.5GHz. RAM: 64GB DDR5. Storage: 2TB NVMe SSD. Network: 10Gbps. Power: 650W.'",
     "Server Summary: High-performance workstation with 8-core 3.5GHz CPU, 64GB DDR5 RAM, 2TB NVMe storage, 10Gbps networking. TDP: 650W. Suitable for ML training and data processing workloads."),
    ("Process in sequence: Extract entities from the text, classify them, then generate a structured output: 'John Smith, CTO of TechCorp, announced at the Berlin conference that they will release v3.0 in March 2025.'",
     "Entities: Person(John Smith, role=CTO), Organization(TechCorp), Location(Berlin), Product(v3.0), Date(March 2025). Event type: Product announcement."),
    ("Multi-step analysis: Read the A/B test results, calculate uplift, then make a recommendation: 'Control: 1000 users, 50 conversions. Variant: 1000 users, 72 conversions.'",
     "Control CVR: 5.0%, Variant CVR: 7.2%. Relative uplift: +44%. Statistically significant (p<0.05 with n=2000). Recommendation: Ship the variant — strong positive impact on conversions."),
]
for instr, ref in chain_pairs:
    add("chain_summarize", instr, ref, difficulty=0.7, num_agents=3)

# --- Relay Translate ---
relay_pairs = [
    ("Relay translate through 3 steps: Technical English → Simple English → Korean: 'The API gateway implements rate limiting with a token bucket algorithm at 1000 RPM.'",
     "API 게이트웨이는 분당 1000개 요청 제한을 토큰 버킷 방식으로 관리합니다."),
    ("Multi-step translation: Code → Pseudocode → Natural language: 'def bfs(graph, start): queue = [start]; visited = {start}; while queue: node = queue.pop(0); for n in graph[node]: if n not in visited: visited.add(n); queue.append(n)'",
     "This algorithm explores a graph level by level. Starting from an initial node, it visits all neighbors before moving deeper. It uses a queue to track which nodes to visit next and a set to avoid revisiting."),
    ("Relay: Mathematical notation → Code → Plain English: '∀x ∈ S : f(x) > 0 ⟹ x ∈ S⁺'",
     "For every element x in set S, if f(x) is positive, then x belongs to the positive subset S⁺. In code: S_plus = [x for x in S if f(x) > 0]."),
    ("Multi-hop translate: SQL → Natural language → Action items: 'SELECT department, COUNT(*) as cnt, AVG(salary) as avg_sal FROM employees WHERE hire_date > 2023-01-01 GROUP BY department HAVING cnt < 5'",
     "Find departments with fewer than 5 employees hired after Jan 2023. Action: 1) Review understaffed departments. 2) Plan hiring for teams below threshold. 3) Check if low headcount correlates with higher avg salary."),
]
for instr, ref in relay_pairs:
    add("relay_translate", instr, ref, difficulty=0.7, num_agents=3)

# --- Multi-step QA ---
multistep_qa_pairs = [
    ("Given these facts: (1) All neural networks use activation functions. (2) ReLU is the most common activation function. (3) Transformers are neural networks. What activation function do transformers commonly use?",
     "Transformers commonly use ReLU (and its variants like GELU). From fact 3, transformers are neural networks. From fact 1, they use activation functions. From fact 2, ReLU is most common."),
    ("Multi-step: First calculate, then explain. A model has 175B parameters, each stored as float16 (2 bytes). How much GPU memory is needed just for model weights? Is one A100-80GB enough?",
     "175B × 2 bytes = 350GB. One A100-80GB provides 80GB — not enough. Need minimum 5 A100-80GB GPUs for model weights alone (plus overhead for activations, optimizer states). This is why model parallelism is necessary."),
    ("Reasoning chain: If a REST API returns 429 status, and the Retry-After header says 60, and our system has no retry logic, and the upstream service requires this API — what happens?",
     "Cascade failure. 429 = rate limited. Without retry logic, the request fails permanently. The upstream service depending on this data also fails. Fix: Implement exponential backoff retry with Retry-After header respect. Add circuit breaker pattern."),
    ("Step-by-step: A Docker container uses 2GB RAM, runs 3 replicas behind a load balancer, with 500MB for the LB itself. If each replica handles 100 RPS, what's the total RAM and max RPS?",
     "RAM: 3 × 2GB + 0.5GB = 6.5GB total. Max throughput: 3 × 100 = 300 RPS. With overhead and safety margin (~70% load target), practical capacity is ~210 RPS sustained."),
    ("Multi-hop: If LoRA rank=16 and the target layer is 4096×4096, how many trainable parameters does LoRA add for this one layer? Compare to full fine-tuning.",
     "LoRA adds two matrices: A (4096×16) + B (16×4096) = 65,536 + 65,536 = 131,072 params. Full fine-tuning: 4096×4096 = 16,777,216 params. LoRA uses 0.78% of full params — 128× reduction."),
]
for instr, ref in multistep_qa_pairs:
    add("multi_step_qa", instr, ref, difficulty=0.8, num_agents=2)

# --- Reasoning ---
reasoning_pairs = [
    ("If all roses are flowers and some flowers fade quickly, can we conclude that some roses fade quickly?",
     "No. 'Some flowers fade quickly' doesn't specify which flowers. The fading flowers might not include roses. This is the fallacy of the undistributed middle."),
    ("A train leaves Station A at 9:00 AM going 60 mph. Another leaves Station B (300 miles away) at 10:00 AM going 90 mph toward Station A. When and where do they meet?",
     "At 10AM, Train A has covered 60mi (240mi remaining). Combined speed: 150mph. Time to meet: 240/150 = 1.6 hours = 1h36min after 10AM = 11:36 AM. Location: 60 + 60×1.6 = 156 miles from A."),
    ("Three servers: A (99.9% uptime), B (99.95%), C (99.99%). If they're in series (all must work), what's the combined uptime? In parallel (any one works)?",
     "Ser1es: 0.999 × 0.9995 × 0.9999 = 99.84% (~14 hours downtime/year). Parallel: 1 - (0.001 × 0.0005 × 0.0001) = 99.99999995% (virtually zero downtime). Redundancy massively improves reliability."),
    ("A function runs in O(n²) on 1000 items in 1 second. How long will it take on 10000 items? On 1 million?",
     "O(n²): 10× input → 100× time. 10000 items: (10000/1000)² = 100 seconds. 1M items: (1000000/1000)² = 1,000,000 seconds ≈ 11.6 days. This is why O(n²) doesn't scale."),
    ("If a hash table has a load factor of 0.75 with 1000 buckets, how many elements does it hold? At what point should it resize?",
     "Current elements: 0.75 × 1000 = 750. Standard practice: resize when load factor exceeds 0.75 (Java HashMap default). So resize at 751 elements, typically doubling to 2000 buckets, bringing load factor to 0.375."),
    ("Company profits: Year 1 = $1M, Year 2 = $1.2M, Year 3 = $0.9M, Year 4 = $1.5M. What's the CAGR?",
     "CAGR = (End/Start)^(1/years) - 1 = (1.5/1.0)^(1/3) - 1 = 1.5^0.333 - 1 ≈ 14.5%. Despite the Year 3 dip, compound annual growth is 14.5%."),
]
for instr, ref in reasoning_pairs:
    add("reasoning", instr, ref, difficulty=0.8)


# ══════════════════════════════════════════════════════════════
#  Phase 3 — Generalize (creative_writing, math + all above)
# ══════════════════════════════════════════════════════════════

# --- Creative Writing ---
creative_pairs = [
    ("Write a 2-sentence product description for a smart water bottle that tracks hydration.",
     "Stay perfectly hydrated with AquaSync — the smart bottle that tracks every sip and sends gentle reminders to your phone. Its sleek design and 24-hour battery make healthy hydration effortless."),
    ("Write a haiku about debugging code.",
     "Bug hides in plain sight / Console logs illuminate / Fixed with one semicolon"),
    ("Write a git commit message for: Fixed the login page to properly validate email format before submitting the form.",
     "fix(auth): validate email format on login form before submission"),
    ("Write a one-paragraph README intro for an open-source AI communication protocol library.",
     "Ogenti is an open-source protocol that enables AI models to communicate with each other using a compressed, emergent language. Instead of exchanging verbose natural language, Ogenti-equipped models transmit compact protocol messages that preserve semantic meaning at a fraction of the token cost. Attach the universal adapter to any language model and join the network."),
    ("Write error messages for: 1) File not found, 2) Rate limited, 3) Invalid input.",
     "1) 'The file you're looking for doesn't exist. Check the path and try again.' 2) 'You've made too many requests. Please wait a moment before trying again.' 3) 'The input format isn't valid. Please check the requirements and resubmit.'"),
    ("Write a metaphor explaining how a neural network learns.",
     "A neural network learns like a sculptor chipping away at marble — starting with a rough block, each training example is a chisel strike that removes a tiny piece of error, gradually revealing the pattern hidden inside the data."),
]
for instr, ref in creative_pairs:
    add("creative_writing", instr, ref, difficulty=0.6)

# --- Math ---
math_pairs = [
    ("Calculate: If a model processes 1000 tokens/second and a prompt is 4096 tokens, how long does inference take? What about batching 8 prompts?",
     "Single: 4096/1000 = 4.096 seconds. Batched (8 prompts): With GPU parallelism, near-linear scaling gives ~4.5-5s total (not 8×). Per-prompt latency drops to ~0.6s. Batching is ~6.8× more efficient."),
    ("A LoRA adapter with rank 8 on a 4096-dim model: how many parameters per layer? Total for 32 layers targeting q,k,v,o?",
     "Per matrix: 4096×8 + 8×4096 = 65,536 params. Per layer (q,k,v,o): 4 × 65,536 = 262,144. Total (32 layers): 32 × 262,144 = 8,388,608 ≈ 8.4M trainable params."),
    ("Cross-entropy loss: Model predicts [0.7, 0.2, 0.1] for classes [A, B, C]. True label is A. What is the loss?",
     "CE = -log(p_true) = -log(0.7) = 0.357. If true label were C: -log(0.1) = 2.303. Lower probability predictions have much higher loss, driving the model to be confident on correct classes."),
    ("Calculate the FLOPs for a single transformer attention layer: seq_len=2048, d_model=4096, num_heads=32.",
     "QKV projections: 3 × 2 × 2048 × 4096² ≈ 206B. Attention scores: 2 × 32 × 2048² × 128 ≈ 34B. Output projection: 2 × 2048 × 4096² ≈ 69B. Total: ~309B FLOPs per layer."),
    ("If training costs $2/GPU-hour on an A100, and training takes 48 GPU-hours, what's the total? How much would 4× A100 parallel training cost if it achieves 3.5× speedup?",
     "Single GPU: 48 × $2 = $96. 4× A100: Time = 48/3.5 = 13.7 hours. Cost = 4 GPUs × 13.7h × $2 = $109.6. Parallelism costs 14% more but finishes 3.5× faster — usually worth it for iteration speed."),
    ("Softmax of [2.0, 1.0, 0.5]: calculate each probability.",
     "exp(2.0)=7.389, exp(1.0)=2.718, exp(0.5)=1.649. Sum=11.756. P=[0.629, 0.231, 0.140]. Softmax amplifies differences — the highest logit gets ~63% probability."),
]
for instr, ref in math_pairs:
    add("math", instr, ref, difficulty=0.7)


# ══════════════════════════════════════════════════════════════
#  Additional diverse tasks for robustness
# ══════════════════════════════════════════════════════════════

extra_summarize = [
    ("Summarize: Redis is an in-memory data structure store used as a database, cache, message broker, and streaming engine. It supports strings, hashes, lists, sets, sorted sets, bitmaps, and HyperLogLogs.",
     "Redis is a versatile in-memory store supporting multiple data structures, used for caching, messaging, and streaming."),
    ("Summarize: OAuth 2.0 is an authorization framework that enables third-party applications to obtain limited access to web services. It works by delegating user authentication to the service that hosts the account.",
     "OAuth 2.0 lets third-party apps access web services with limited permissions by delegating auth to the account host."),
    ("Summarize: Attention mechanisms in neural networks allow models to focus on relevant parts of the input when producing output. They compute weighted combinations of values based on query-key similarity scores.",
     "Attention lets neural networks focus on relevant input parts by computing similarity-weighted value combinations."),
]
for instr, ref in extra_summarize:
    add("summarize", instr, ref, difficulty=0.35)

extra_qa = [
    ("What is the difference between TCP and UDP?", "TCP is connection-oriented with guaranteed delivery and ordering. UDP is connectionless with no guarantees but lower latency."),
    ("What is a race condition?", "A race condition occurs when multiple threads access shared data concurrently and the outcome depends on the timing of their execution."),
    ("What does ACID stand for in databases?", "Atomicity, Consistency, Isolation, Durability."),
    ("What is the difference between authentication and authorization?", "Authentication verifies who you are (identity). Authorization determines what you can do (permissions)."),
    ("What is a deadlock?", "A deadlock occurs when two or more processes are unable to proceed because each is waiting for the other to release a resource."),
]
for instr, ref in extra_qa:
    add("qa", instr, ref, difficulty=0.3)


# ══════════════════════════════════════════════════════════════
#  Generate output files
# ══════════════════════════════════════════════════════════════

def main():
    random.seed(42)
    random.shuffle(TASKS)

    # Split: 85% train, 15% eval
    split = int(len(TASKS) * 0.85)
    train_tasks = TASKS[:split]
    eval_tasks = TASKS[split:]

    out_dir = Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(exist_ok=True)

    # Write train.jsonl
    train_path = out_dir / "train.jsonl"
    with open(train_path, "w", encoding="utf-8") as f:
        for t in train_tasks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(f"✓ {train_path}: {len(train_tasks)} tasks")

    # Write eval.jsonl
    eval_path = out_dir / "eval.jsonl"
    with open(eval_path, "w", encoding="utf-8") as f:
        for t in eval_tasks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(f"✓ {eval_path}: {len(eval_tasks)} tasks")

    # Stats
    from collections import Counter
    cats = Counter(t["category"] for t in TASKS)
    print(f"\nTotal: {len(TASKS)} tasks across {len(cats)} categories:")
    for cat, count in cats.most_common():
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    main()
