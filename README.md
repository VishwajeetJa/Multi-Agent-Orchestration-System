# 🤖 Multi-Agent Orchestration System (Agentic AI)
**An asynchronous, multi-stage AI pipeline for automated research and report synthesis.**

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Celery](https://img.shields.io/badge/Worker-Celery-green.svg)](https://docs.celeryq.dev/)
[![Redis](https://img.shields.io/badge/Queue-Redis-red.svg)](https://redis.io/)
[![Flask](https://img.shields.io/badge/API-Flask-lightgrey.svg)](https://flask.palletsprojects.com/)

## 📋 Project Overview
This project implements a **Manager-Worker Agentic Workflow** that breaks down complex user queries into a structured, three-stage pipeline. By leveraging a distributed task queue (Celery + Redis), the system handles long-running LLM operations asynchronously, providing a scalable solution for AI-driven research.

## 🏗️ System Architecture

The system is built on a decoupled architecture to ensure high reliability:

1.  **Manager Agent (Flask API):** The system's entry point. It receives user queries, validates parameters, and orchestrates the task lifecycle by assigning unique `task_ids`.
2.  **Message Broker (Redis):** A high-performance data store that manages the communication between the API and background workers.
3.  **Worker Cluster (Celery):** A pool of background processes executing the specialized Agentic Chain:
    * 🔍 **Retriever Agent:** Gathers raw technical data and domain-specific facts.
    * 📊 **Analyzer Agent:** Processes raw data to extract strategic insights and patterns.
    * ✍️ **Writer Agent:** Synthesizes the analysis into a professional, stakeholder-ready report.


## 🚀 Getting Started

### Prerequisites
* **OS:** WSL2 (Ubuntu 22.04+)
* **Python:** 3.12+
* **Services:** Redis Server

### Installation
```bash
# Clone the repository
git clone [https://github.com/VishwajeetJa/agentic_ai.git](https://github.com/VishwajeetJa/agentic_ai.git)
cd agentic_ai

# Setup Virtual Environment
python3 -m venv venv
source venv/bin/activate

# Install Dependencies
pip install -r requirements.txt

Execution Guide
To run the system, open four separate Ubuntu terminals and execute the following:
Terminal,Component,Command
1,Redis,sudo service redis-server start
2,Workers,celery -A tasks worker --loglevel=info
3,Manager,python app.py
4,Test/Client,"curl -X POST http://127.0.0.1:5000/process -d '{""query"": ""Quantum Computing Impact""}'"

🛠️ Key Technical Features
Asynchronous Execution: Prevents API timeouts during intensive LLM processing.

Role-Based Agent Specialization: Utilizes distinct system prompts for each agent to ensure depth and reduce hallucinations.

Task Persistence: Powered by Redis, ensuring tasks survive even if the API server restarts.

Developed by: Vishwajeet Jadhav

Major: AI and Data Science

Institution: Vidya Pratishthan's Kamalnayan Bajaj Institute of Engineering & Technology