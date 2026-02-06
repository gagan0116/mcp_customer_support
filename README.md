# VARA.ai - AI-Powered Customer Support Automation

![Gemini 3](https://img.shields.io/badge/Gemini%203-Powered-blue?style=for-the-badge&logo=google)
![Python](https://img.shields.io/badge/Python-3.11+-green?style=for-the-badge&logo=python)
![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-purple?style=for-the-badge)
![Multi-Agent](https://img.shields.io/badge/Multi--Agent-5%20Agents-orange?style=for-the-badge)

> **Google DeepMind Gemini 3 Hackathon Submission**

## 🚀 Live Demo

- **Live Application:** [https://storage.googleapis.com/mcp_frontend/index.html](https://storage.googleapis.com/mcp_frontend/index.html)
- **Policy Compiler:** [https://policy-compiler-171083103370.northamerica-northeast1.run.app](https://policy-compiler-171083103370.northamerica-northeast1.run.app)
- **Demo Video:** [YouTube Demo](#) <!-- Add your YouTube link here -->

---

## 📋 Problem Statement

Customer support teams spend **70%+ of their time** on repetitive refund/return requests. Each request requires:
- Reading customer emails with attachments
- Cross-referencing order databases
- Consulting return policy documents
- Making consistent decisions

**VARA.ai automates this entire workflow using Gemini 3's advanced reasoning capabilities.**

---

## 💡 Solution Overview

VARA.ai is an end-to-end AI system that:

1. **Monitors Gmail** for incoming refund/return requests
2. **Classifies emails** using Gemini's understanding capabilities
3. **Extracts order details** from email text and invoice attachments (Gemini Vision)
4. **Verifies against database** using MCP-connected PostgreSQL
5. **Adjudicates requests** by traversing a policy knowledge graph
6. **Records decisions** with full reasoning transparency

---

## 🧠 Gemini 3 Integration

| Feature | Model Used | Purpose |
|---------|------------|---------|
| **Extended Thinking** | `gemini-3-pro-preview` | Multi-step policy adjudication with `thinking_level="high"` |
| **Structured Output** | `gemini-2.5-flash` | JSON schema extraction for order details |
| **Image Understanding** | `gemini-2.0-flash` | Invoice/receipt parsing via Gemini Vision |
| **Classification** | `gemini-3-flash-preview` | Email intent classification (REFUND/RETURN/REPLACEMENT) |
| **Ontology Design** | `gemini-2.5-flash` | Policy knowledge graph schema generation |

### Key Gemini 3 Features Used:
- `ThinkingConfig(thinking_level="high")` - Extended reasoning for complex decisions
- `response_schema` - Guaranteed structured JSON outputs
- `response_mime_type="application/json"` - Reliable parsing
- `system_instruction` - Agent persona and behavior control
- **Gemini Vision** - Multi-modal invoice/attachment processing

---

## 🤖 Multi-Agent Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    POLICY COMPILER PIPELINE                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│   │   Ontology   │───▶│  Extraction  │───▶│    Critic    │     │
│   │    Agent     │    │    Agent     │    │    Agent     │     │
│   │              │    │              │    │              │     │
│   │ Designs      │    │ Extracts     │    │ Validates    │     │
│   │ Knowledge    │    │ Policy       │    │ & Suggests   │     │
│   │ Graph Schema │    │ Entities     │    │ Improvements │     │
│   └──────────────┘    └──────────────┘    └──────┬───────┘     │
│                                                   │              │
│                                           ┌──────▼───────┐      │
│                                           │   Builder    │      │
│                                           │    Agent     │      │
│                                           │              │      │
│                                           │ Constructs   │      │
│                                           │ Neo4j Graph  │      │
│                                           └──────────────┘      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    REQUEST PROCESSING                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────────┐                                              │
│   │ Adjudicator  │  Uses Extended Thinking (thinking_level=high)│
│   │    Agent     │  to traverse policy graph and make decisions │
│   │              │  with full reasoning transparency             │
│   └──────────────┘                                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**5 Specialized Agents:**
1. **Ontology Agent** - Designs knowledge graph schema from policy documents
2. **Extraction Agent** - Extracts policy rules, conditions, and relationships
3. **Critic Agent** - Validates extraction quality and suggests improvements
4. **Builder Agent** - Constructs Neo4j knowledge graph with Cypher queries
5. **Adjudicator Agent** - Makes refund decisions using extended thinking

---

## 🔧 MCP (Model Context Protocol) Integration

VARA.ai uses **FastMCP** to create modular, tool-based AI capabilities:

| MCP Server | Purpose | Key Tools |
|------------|---------|-----------|
| `db_verification_server` | Order database access | `find_order_by_invoice_number`, `verify_from_email_matches_customer` |
| `neo4j_graph_engine` | Policy knowledge graph | `execute_cypher_query`, `create_node`, `create_relationship` |
| `policy_engine` | PDF document parsing | `parse_all_policy_documents` |

---

## 🛠️ Tech Stack

### Core AI/ML
| Technology | Purpose |
|------------|---------|
| Gemini 3 API | LLM backbone (classification, extraction, reasoning) |
| google-genai | Official Python SDK for Gemini |
| Multi-Agent System | 5 specialized agents for policy compilation |

### Infrastructure
| Technology | Purpose |
|------------|---------|
| Google Cloud Run | Serverless container deployment |
| Google Cloud Pub/Sub | Event-driven email triggers |
| Google Cloud Tasks | Async job queue |
| Google Cloud SQL | PostgreSQL database |
| Google Cloud Storage | Email/artifact storage |
| Firestore | Gmail history state tracking |
| Docker | Container packaging |

### Databases
| Technology | Purpose |
|------------|---------|
| PostgreSQL (pg8000) | Customer orders & refund cases |
| Neo4j Aura | Policy knowledge graph |

### Frameworks
| Technology | Purpose |
|------------|---------|
| FastAPI | REST API framework |
| uvicorn | ASGI server |
| FastMCP (mcp[cli]) | MCP server implementation |
| SSE-Starlette | Server-sent events |

### Document Processing
| Technology | Purpose |
|------------|---------|
| LlamaParse | PDF policy document extraction |
| pypdf | PDF utility operations |
| BeautifulSoup4 | HTML parsing |

### APIs & Auth
| Technology | Purpose |
|------------|---------|
| Gmail API | Email monitoring & retrieval |
| OAuth 2.0 | Google authentication |

---

## 📁 Project Structure

```
mcp_customer_support/
├── gmail-event-processor/    # Email ingestion (Cloud Run)
│   ├── app.py                # FastAPI Pub/Sub endpoint
│   ├── classifier.py         # Gemini email classification
│   ├── gmail_processor.py    # Gmail API integration
│   └── history_store.py      # Firestore state tracking
│
├── mcp_processor/            # Main processing (Cloud Run)
│   ├── app.py                # Cloud Tasks endpoint
│   └── processor.py          # MCPProcessor orchestrator
│
├── policy_compiler_agents/   # Multi-agent system
│   ├── ontology_agent.py     # Knowledge graph schema design
│   ├── extraction_agent.py   # Policy rule extraction
│   ├── critic_agent.py       # Quality validation
│   ├── builder_agent.py      # Neo4j graph construction
│   └── adjudicator_agent.py  # Decision making with extended thinking
│
├── db_verification/          # MCP Server - Database
├── neo4j_graph_engine/       # MCP Server - Graph DB
├── policy_engine/            # MCP Server - PDF Parser
├── knowledge_base_server/    # Policy compiler web service
│
├── policy_docs/              # Return policy PDFs
├── artifacts/                # Processing outputs & evidence
└── web_dashboard_ui/         # Frontend interface
```

---

## 🚀 Local Development Setup

### Prerequisites

- Python 3.11+
- Docker (optional, for containerized deployment)
- Google Cloud account with enabled APIs
- Neo4j Aura instance
- LlamaParse API key

### Installation

```bash
# Clone the repository
git clone https://github.com/gagan0116/mcp_customer_support.git
cd mcp_customer_support

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the project root:

```env
# Gemini API
GEMINI_API_KEY=your_gemini_api_key

# Neo4j Aura
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password

# Cloud SQL (PostgreSQL)
CLOUD_INSTANCE=project:region:instance
CLOUD_DB_NAME=refunds_db
CLOUD_DB_USER=postgres
CLOUD_DB_PASS=your_db_password

# LlamaParse
LLAMA_CLOUD_API_KEY=your_llamaparse_key

# Google Cloud Storage
GCS_BUCKET_NAME=your_bucket_name
```

### Running Locally

```bash
# Run the MCP client (interactive testing)
python mcp_client.py

# Run the policy compiler web service
cd knowledge_base_server
python main.py
```

---

## 🧪 Testing Instructions

### For Judges - Live Demo

1. **Visit the live application:** [https://storage.googleapis.com/mcp_frontend/index.html](https://storage.googleapis.com/mcp_frontend/index.html)

2. **Policy Compiler Demo:**
   - Navigate to [Policy Compiler](https://policy-compiler-171083103370.northamerica-northeast1.run.app)
   - Upload a return policy PDF
   - Watch the multi-agent system build a knowledge graph
   - View the interactive graph visualization

3. **End-to-End Flow:**
   - Send a refund request email with an invoice attachment
   - System automatically classifies, extracts, verifies, and adjudicates
   - View the decision with full reasoning transparency

### Sample Test Scenarios

| Scenario | Expected Outcome |
|----------|------------------|
| Electronics return within 30 days | APPROVED - Standard return window |
| Perishable food item | DENIED - Non-returnable category |
| Premium member after 45 days | APPROVED - Extended window for premium |
| Missing invoice attachment | PARTIAL - Request more information |

---

## 📊 Sample Outputs

The `artifacts/` folder contains real processing examples:

- `extracted_order.json` - Gemini's structured order extraction
- `verified_order.json` - Database verification results
- `adjudication_decision.json` - Final decision with reasoning
- `knowledge_graph/graph_visualization.html` - Interactive policy graph

---

## 👥 Team

| Name | Role |
|------|------|
| Gagan | Developer |

---

## 📄 License

MIT License - See LICENSE file for details

---

## 🔗 Links

- **GitHub:** [https://github.com/gagan0116/mcp_customer_support](https://github.com/gagan0116/mcp_customer_support)
- **Live Demo:** [https://storage.googleapis.com/mcp_frontend/index.html](https://storage.googleapis.com/mcp_frontend/index.html)
- **Hackathon:** [Google DeepMind Gemini 3 Hackathon](https://googlegemini3.devpost.com/)
