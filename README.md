# High-Level Design (HLD) - MCP Customer Support System

## Executive Overview

This application is an **AI-powered Customer Support Automation System** that processes customer refund/return requests via email, verifies them against order databases, adjudicates requests using a policy knowledge graph, and stores decisions for downstream processing.

---

## System Architecture Diagram

```mermaid
flowchart TB
    subgraph External["External Data Sources"]
        Gmail["Gmail API"]
        PDF["Policy PDFs"]
    end

    subgraph CloudEvents["Cloud Event Layer"]
        PubSub["Google Cloud Pub/Sub"]
        CloudTasks["Cloud Tasks Queue"]
    end

    subgraph ProcessingLayer["Processing Layer (Cloud Run)"]
        GmailProcessor["gmail-event-processor<br/>Cloud Run Service"]
        MCPProcessor["mcp-processor<br/>Cloud Run Service"]
    end

    subgraph StorageLayer["Storage Layer"]
        GCS["Cloud Storage<br/>(refunds_bucket)"]
        CloudSQL["Cloud SQL PostgreSQL<br/>(refunds_db)"]
        Neo4j["Neo4j Aura<br/>(Policy Knowledge Graph)"]
    end

    subgraph MCPServers["MCP Server Layer (Stdio Transport)"]
        DBVerification["db_verification_server<br/>(Order Lookup MCP)"]
        Neo4jMCP["neo4j_graph_engine<br/>(Graph Query MCP)"]
        PolicyEngine["policy_engine<br/>(PDF Parser MCP)"]
    end

    subgraph AILayer["AI/LLM Layer"]
        Gemini["Google Gemini API<br/>(Classification, Extraction, Adjudication)"]
        LlamaParse["LlamaParse API<br/>(PDF Parsing)"]
    end

    subgraph AgentLayer["Policy Compiler Agents"]
        Ontology["ontology_agent<br/>(Schema Design)"]
        Extraction["extraction_agent<br/>(Entity Extraction)"]
        Adjudicator["adjudicator_agent<br/>(Decision Making)"]
        GraphTraversal["graph_traversal<br/>(Policy Lookup)"]
    end

    Gmail -->|Push Notification| PubSub
    PubSub -->|Trigger| GmailProcessor
    GmailProcessor -->|Read Emails| Gmail
    GmailProcessor -->|Classify Email| Gemini
    GmailProcessor -->|Store JSON| GCS
    GmailProcessor -->|Enqueue Task| CloudTasks
    CloudTasks -->|Trigger| MCPProcessor
    MCPProcessor -->|Read JSON| GCS
    MCPProcessor -->|Extract Details| Gemini
    MCPProcessor -.->|MCP Stdio| DBVerification
    MCPProcessor -.->|MCP Stdio| Neo4jMCP
    DBVerification -->|Query| CloudSQL
    Neo4jMCP -->|Query| Neo4j
    Adjudicator -->|Traverse| GraphTraversal
    GraphTraversal -->|Query| Neo4j
    MCPProcessor -->|Insert Case| CloudSQL
    PolicyEngine -->|Parse| LlamaParse
    PolicyEngine -->|Read| PDF
    Ontology -->|Design Schema| Gemini
    Extraction -->|Extract Entities| Gemini
    Adjudicator -->|Make Decision| Gemini
```

---

## Detailed Component Diagram

```mermaid
flowchart LR
    subgraph EmailFlow["1. Email Ingestion Flow"]
        A1["Gmail Push to Pub/Sub"] --> A2["gmail-event-processor/app.py"]
        A2 --> A3["gmail_processor.py<br/>process_new_emails()"]
        A3 --> A4["classifier.py<br/>classify_email()"]
        A4 --> A5["store_email.py<br/>store_email_result()"]
    end

    subgraph ProcessingFlow["2. MCP Processing Flow"]
        B1["Cloud Tasks Trigger"] --> B2["mcp_processor/app.py"]
        B2 --> B3["processor.py<br/>MCPProcessor"]
        B3 --> B4["extract_order_details()"]
        B4 --> B5["verify_request_with_db()"]
        B5 --> B6["adjudicator_agent.py<br/>AdjudicatorV2"]
        B6 --> B7["insert_refund_case()"]
    end

    subgraph PolicyFlow["3. Policy Compilation Flow"]
        C1["policy_engine/mcp_server.py"] --> C2["parse_all_policy_documents()"]
        C2 --> C3["ontology_agent.py<br/>design_ontology()"]
        C3 --> C4["extraction_agent.py<br/>extract_policy_rules()"]
        C4 --> C5["neo4j_graph_engine/mcp_server.py<br/>create_node(), create_relationship()"]
    end
```

---

## Component Descriptions

### 1. Gmail Event Processor (`gmail-event-processor/`)

| File | Purpose |
|------|---------|
| [app.py](file:///c:/Users/satis/projects/mcp-customer-support/gmail-event-processor/app.py) | FastAPI endpoint `/pubsub/gmail` triggered by Pub/Sub |
| [gmail_processor.py](file:///c:/Users/satis/projects/mcp-customer-support/gmail-event-processor/gmail_processor.py) | Reads Gmail via History API, extracts body/attachments |
| [classifier.py](file:///c:/Users/satis/projects/mcp-customer-support/gmail-event-processor/classifier.py) | LLM-based email classification (RETURN/REFUND/REPLACEMENT/NONE) |
| [store_email.py](file:///c:/Users/satis/projects/mcp-customer-support/gmail-event-processor/store_email.py) | Stores JSON to GCS, enqueues Cloud Task |
| [secret_manager.py](file:///c:/Users/satis/projects/mcp-customer-support/gmail-event-processor/secret_manager.py) | Loads Gmail tokens and Gemini API key from Secret Manager |
| [history_store.py](file:///c:/Users/satis/projects/mcp-customer-support/gmail-event-processor/history_store.py) | Tracks Gmail historyId using Secret Manager |

**Data Flow:**
```mermaid
sequenceDiagram
    participant PS as Pub/Sub
    participant GP as Gmail Processor
    participant Gmail as Gmail API
    participant LLM as Gemini LLM
    participant GCS as Cloud Storage
    participant CT as Cloud Tasks

    PS->>GP: POST /pubsub/gmail
    GP->>Gmail: users.history.list()
    Gmail-->>GP: New messages
    GP->>Gmail: messages.get() + attachments
    GP->>LLM: classify_email(subject, body)
    LLM-->>GP: {category, confidence}
    alt category in [RETURN, REFUND, REPLACEMENT]
        GP->>GCS: Upload JSON blob
        GP->>CT: Create task with blob path
    end
```

---

### 2. MCP Processor (`mcp_processor/`)

| File | Purpose |
|------|---------|
| [app.py](file:///c:/Users/satis/projects/mcp-customer-support/mcp_processor/app.py) | FastAPI endpoint `/process` triggered by Cloud Tasks |
| [processor.py](file:///c:/Users/satis/projects/mcp-customer-support/mcp_processor/processor.py) | Core `MCPProcessor` class orchestrating the refund workflow |

**Key Class: `MCPProcessor`**

```mermaid
classDiagram
    class MCPProcessor {
        +sessions: Dict[str, ClientSession]
        +server_configs: Dict
        +connect_to_all_servers()
        +extract_order_details(combined_text)
        +verify_request_with_db(extracted_data)
        +insert_refund_case(email_data, extracted_data, verified_record, adjudication_result)
        +process_single_email(bucket, blob_path)
        +cleanup()
    }
    
    MCPProcessor --> DBVerificationMCP : "db_verification"
    MCPProcessor --> Neo4jMCP : "neo4j_graph"
    MCPProcessor --> AdjudicatorV2 : adjudication
    MCPProcessor --> GeminiAPI : extraction
```

**Processing Flow:**
```mermaid
sequenceDiagram
    participant CT as Cloud Tasks
    participant MCP as MCP Processor
    participant GCS as Cloud Storage
    participant LLM as Gemini
    participant DB as DB Verification MCP
    participant ADJ as Adjudicator Agent
    participant SQL as Cloud SQL

    CT->>MCP: POST /process {bucket, blob_path}
    MCP->>GCS: Download JSON
    MCP->>LLM: extract_order_details(email_body)
    LLM-->>MCP: {invoice_number, items, dates...}
    MCP->>DB: verify_from_email_matches_customer()
    DB-->>MCP: Customer info
    MCP->>DB: find_order_by_invoice_number()
    DB-->>MCP: Order details
    MCP->>ADJ: adjudicate(verified_order)
    ADJ-->>MCP: {decision, explanation}
    MCP->>SQL: INSERT INTO refund_cases
```

---

### 3. MCP Servers

#### 3.1 DB Verification Server (`db_verification/`)

| File | Purpose |
|------|---------|
| [db_verification_server.py](file:///c:/Users/satis/projects/mcp-customer-support/db_verification/db_verification_server.py) | MCP server exposing order lookup tools |
| [db.py](file:///c:/Users/satis/projects/mcp-customer-support/db_verification/db.py) | Cloud SQL connector using pg8000 |

**Exposed MCP Tools:**
| Tool | Description |
|------|-------------|
| `list_orders_by_customer_email` | Fetch order history for an email |
| `find_order_by_invoice_number` | Lookup single order with full hierarchy |
| `find_order_by_order_invoice_id` | Alternative lookup by order_invoice_id |
| `list_order_items_by_order_invoice_id` | Get line items for an order |
| `verify_from_email_matches_customer` | Check if email exists in customers table |
| `get_customer_orders_with_items` | Deep fetch with order items |
| `select_order_id` | LLM-assisted order matching |
| `llm_find_orders` | Generate SQL from natural language |

---

#### 3.2 Neo4j Graph Engine (`neo4j_graph_engine/`)

| File | Purpose |
|------|---------|
| [mcp_server.py](file:///c:/Users/satis/projects/mcp-customer-support/neo4j_graph_engine/mcp_server.py) | MCP server for Neo4j knowledge graph operations |
| [db.py](file:///c:/Users/satis/projects/mcp-customer-support/neo4j_graph_engine/db.py) | Neo4j async driver singleton |

**Exposed MCP Tools:**
| Tool | Description |
|------|-------------|
| `check_neo4j_connection` | Test database connectivity |
| `get_graph_schema` | Retrieve node labels and relationships |
| `get_graph_statistics` | Node/relationship counts |
| `execute_cypher_query` | Run read-only Cypher |
| `execute_cypher_write` | Run write Cypher (CREATE, MERGE) |
| `execute_cypher_batch` | Bulk graph construction |
| `create_node` | Create/merge a node |
| `create_relationship` | Create relationship between nodes |
| `create_schema_constraints` | Set up indexes |
| `clear_graph` | Delete all data (destructive) |
| `validate_graph_integrity` | Check for missing citations, orphans |
| `sample_graph_data` | Get sample nodes for verification |

---

#### 3.3 Policy Engine (`policy_engine/`)

| File | Purpose |
|------|---------|
| [mcp_server.py](file:///c:/Users/satis/projects/mcp-customer-support/policy_engine/mcp_server.py) | MCP server for PDF policy parsing |

**Exposed MCP Tools:**
| Tool | Description |
|------|-------------|
| `parse_all_policy_documents` | Parse all PDFs in a directory to combined Markdown |
| `parse_single_policy_document` | Parse a single PDF |

---

### 4. Policy Compiler Agents (`policy_compiler_agents/`)

These agents transform policy PDFs into a queryable Neo4j knowledge graph.

```mermaid
flowchart LR
    PDF["Policy PDFs"] --> Parse["LlamaParse"]
    Parse --> MD["Combined Markdown"]
    MD --> OA["Ontology Agent"]
    OA --> Schema["Graph Schema"]
    Schema --> EA["Extraction Agent"]
    EA --> Entities["Entities + Relationships"]
    Entities --> CG["Cypher Generator"]
    CG --> Neo4j["Neo4j Knowledge Graph"]
```

| Agent | File | Purpose |
|-------|------|---------|
| **Ontology Agent** | [ontology_agent.py](file:///c:/Users/satis/projects/mcp-customer-support/policy_compiler_agents/ontology_agent.py) | Designs graph schema (node labels, properties, relationships) using Gemini Thinking Mode |
| **Extraction Agent** | [extraction_agent.py](file:///c:/Users/satis/projects/mcp-customer-support/policy_compiler_agents/extraction_agent.py) | 3-phase pipeline: Triplet Extraction → Graph Linking → Cypher Generation |
| **Adjudicator Agent** | [adjudicator_agent.py](file:///c:/Users/satis/projects/mcp-customer-support/policy_compiler_agents/adjudicator_agent.py) | Makes refund decisions by traversing policy graph and applying LLM reasoning |
| **Graph Traversal** | [graph_traversal.py](file:///c:/Users/satis/projects/mcp-customer-support/policy_compiler_agents/graph_traversal.py) | 3-hop graph traversal from ProductCategory nodes |

**Adjudicator Flow:**
```mermaid
flowchart TB
    Input["Verified Order Data"] --> BuildContext["Build Context<br/>(items, dates, amounts)"]
    BuildContext --> Classify["Classify ProductCategory<br/>(76 categories via LLM)"]
    Classify --> Traverse["3-Hop Graph Traversal<br/>(ReturnWindow, Fee, Restriction)"]
    Traverse --> FetchSource["Fetch Source Text<br/>(from citations)"]
    FetchSource --> Decision["LLM Decision<br/>(APPROVE/DENY/PARTIAL)"]
    Decision --> Explain["Generate Customer Explanation"]
    Explain --> Output["Adjudication Result"]
```

---

### 5. Database Schema

```mermaid
erDiagram
    CUSTOMERS {
        uuid customer_id PK
        string customer_email UK
        string full_name
        string phone
        string membership_tier
        timestamp created_at
    }
    
    ORDERS {
        uuid order_id PK
        string invoice_number UK
        string order_invoice_id
        uuid customer_id FK
        decimal total_amount
        string order_status
        timestamp ordered_at
        timestamp delivered_at
        string seller_type
    }
    
    ORDER_ITEMS {
        uuid order_item_id PK
        uuid order_id FK
        string sku
        string item_name
        decimal unit_price
        int quantity
        jsonb metadata
    }
    
    REFUND_CASES {
        uuid case_id PK
        string request_type
        uuid customer_id FK
        uuid order_id FK
        string decision
        decimal refund_amount
        text explanation
        jsonb raw_email
        jsonb extracted_data
        timestamp created_at
    }
    
    CUSTOMERS ||--o{ ORDERS : has
    ORDERS ||--o{ ORDER_ITEMS : contains
    CUSTOMERS ||--o{ REFUND_CASES : files
    ORDERS ||--o{ REFUND_CASES : references
```

---

### 6. Knowledge Graph Schema

```mermaid
graph TB
    PC["ProductCategory"] -->|HAS_WINDOW| RW["ReturnWindow"]
    PC -->|HAS_FEE| RF["RestockingFee"]
    PC -->|HAS_RESTRICTION| RR["Restriction"]
    PC -->|REQUIRES| RC["Condition"]
    
    RW -->|EXTENDED_FOR| MT["MembershipTier"]
    RF -->|WAIVED_IF| RC
    RF -->|WAIVED_FOR| MT
    
    RC -->|APPLIES_TO| PC
    
    style PC fill:#e1f5fe
    style RW fill:#c8e6c9
    style RF fill:#ffccbc
    style RR fill:#f8bbd9
    style MT fill:#fff9c4
    style RC fill:#d1c4e9
```

---

### 7. Infrastructure & Deployment

| Component | Deployment Target | Config File |
|-----------|-------------------|-------------|
| Gmail Processor | Cloud Run | [cloudbuild.yaml](file:///c:/Users/satis/projects/mcp-customer-support/cloudbuild.yaml) |
| MCP Processor | Cloud Run | [cloudbuild_mcp_processor.yaml](file:///c:/Users/satis/projects/mcp-customer-support/cloudbuild_mcp_processor.yaml) |
| Cloud Tasks Queue | Cloud Tasks | [create_queue.sh](file:///c:/Users/satis/projects/mcp-customer-support/infrastructure/create_queue.sh) |
| Master Deploy | Shell Script | [deploy.sh](file:///c:/Users/satis/projects/mcp-customer-support/infrastructure/deploy.sh) |

**Environment Variables:**

| Service | Key Variables |
|---------|---------------|
| Gmail Processor | `MCP_QUEUE_NAME`, `MCP_PROCESSOR_URL` |
| MCP Processor | `GEMINI_API_KEY`, `CLOUD_INSTANCE`, `CLOUD_DB_*`, `NEO4J_*`, `GCS_BUCKET_NAME` |

---

## Data Flow Summary

```mermaid
flowchart TB
    subgraph Ingestion["📧 Email Ingestion"]
        E1["Customer sends email"] --> E2["Gmail Push Notification"]
        E2 --> E3["Pub/Sub triggers Cloud Run"]
        E3 --> E4["Classify with Gemini"]
        E4 --> E5["Store JSON to GCS"]
        E5 --> E6["Enqueue Cloud Task"]
    end
    
    subgraph Processing["⚙️ Refund Processing"]
        P1["Cloud Task triggers MCP Processor"] --> P2["Download email JSON"]
        P2 --> P3["Extract order details (LLM)"]
        P3 --> P4["Verify customer in DB"]
        P4 --> P5["Lookup order by invoice"]
        P5 --> P6["Adjudicate against policy graph"]
        P6 --> P7["Insert refund_case record"]
    end
    
    subgraph PolicySetup["📚 Policy Setup (One-time)"]
        S1["Upload policy PDFs"] --> S2["Parse with LlamaParse"]
        S2 --> S3["Design ontology schema"]
        S3 --> S4["Extract entities & relationships"]
        S4 --> S5["Build Neo4j knowledge graph"]
    end
    
    E6 --> P1
    S5 -.->|"Query at runtime"| P6
```

---

## Key Technologies

| Category | Technology |
|----------|------------|
| **Cloud Platform** | Google Cloud Platform (Cloud Run, Cloud Tasks, Pub/Sub, Cloud SQL, Secret Manager, Cloud Build) |
| **LLM/AI** | Google Gemini (gemini-2.0-flash, gemini-3-pro-preview) |
| **Graph Database** | Neo4j Aura |
| **PDF Parsing** | LlamaParse |
| **MCP Framework** | FastMCP (Model Context Protocol) |
| **Web Framework** | FastAPI + Uvicorn |
| **Container** | Docker |

---

## File Reference Index

| Category | Files |
|----------|-------|
| **Gmail Processing** | `gmail-event-processor/app.py`, `gmail_processor.py`, `classifier.py`, `store_email.py` |
| **MCP Processing** | `mcp_processor/app.py`, `processor.py` |
| **MCP Servers** | `db_verification/db_verification_server.py`, `neo4j_graph_engine/mcp_server.py`, `policy_engine/mcp_server.py` |
| **Policy Agents** | `policy_compiler_agents/ontology_agent.py`, `extraction_agent.py`, `adjudicator_agent.py`, `graph_traversal.py` |
| **Database** | `db_verification/db.py`, `neo4j_graph_engine/db.py` |
| **Infrastructure** | `cloudbuild.yaml`, `cloudbuild_mcp_processor.yaml`, `infrastructure/deploy.sh` |
| **Standalone/Dev** | `mcp_client/client.py`, `check_email_llm.py` |
