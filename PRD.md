# 🦋 Product Requirements Document (PRD)

# Squad Hunza — The Fair First-Round Recruiter
> **AI Recruitment Email Assistant for Solo Recruiters & Small Talent Teams**

---

| Document Metadata | Details |
| :--- | :--- |
| **Product Name** | Squad Hunza — The Fair First-Round Recruiter |
| **Version** | 1.0.0 |
| **Status** | Active / Baseline |
| **Target Audience** | Solo HR Managers, Small Agency Recruiters, Startup Talent Leads |
| **Tech Stack** | FastAPI, Supabase (PostgreSQL + pgvector), Redis, Celery, LangChain, Groq LLM |
| **Repository** | `Comebck-Pakistan/cohort-1-squad-hunza` |

---

## 🎯 1. Executive Summary

### 1.1 Problem Statement
Solo recruiters and HR managers at small agencies process 2.7x more applications than 3 years ago while working in smaller teams. Managing job candidates via raw Gmail inboxes and manual spreadsheets creates massive bottlenecks:
- **Delayed Candidate Communication:** Genuine candidates wait days or weeks for responses, often accepting competing offers or suffering from recruiter "ghosting".
- **Repetitive Administrative Overhead:** Recruiters spend 15+ hours/week manually categorizing emails, reading CVs, writing personalized responses (acknowledgements, interview invites, rejections), and updating candidate statuses.
- **Inbox Chaos:** Critical candidate queries, interview confirmations, and follow-ups get lost in unorganized Gmail inboxes.

### 1.2 Product Vision
**The Fair First-Round Recruiter** is an intelligent AI assistant that seamlessly integrates with a recruiter's email inboxes (Gmail and Microsoft Outlook / 365). It automatically categorizes incoming emails, parses candidate resumes, drafts personalized responses in the recruiter's voice, and presents a **Human-in-the-Loop** dashboard where recruiters review and approve responses with a single click. Additionally, it offers a **Hybrid RAG Chat Assistant** allowing recruiters to query their inbox data in plain English.

---

## 👤 2. Target User & Persona

| Field | Detail |
| :--- | :--- |
| **Primary User** | Solo HR Manager / Small Agency Recruiter |
| **Key Characteristics** | Manages 5–15 open positions simultaneously; receives 100+ emails/day in Gmail or Outlook; lacks enterprise ATS software (e.g., Greenhouse/Lever). |
| **Core Need** | Instant organization of recruitment emails, automated draft generation, and zero manual status tracking without giving up control over final communications. |
| **Primary Goal** | Reduce candidate response time from days to under 1 hour while saving 2+ hours of administrative work daily. |

---

## 🔑 3. Key Features & Functional Requirements

### 3.1 Feature 1: Google OAuth & Secure Gmail Integration
* **FR-1.1:** Secure single-sign-on (SSO) using Google OAuth 2.0.
* **FR-1.2:** Scoped permissions for reading emails, managing Gmail labels, and sending approved drafts via the Gmail API.
* **FR-1.3:** Encryption of user tokens (access & refresh tokens) at rest using AES-256 (`cryptography` package).
* **FR-1.4:** Token auto-refresh mechanism preventing session interruption during background processing.

### 3.2 Feature 2: Microsoft OAuth & Secure Outlook Integration
* **FR-2.1:** Microsoft Identity OAuth 2.0 consent flow supporting Microsoft 365 corporate and Outlook.com personal accounts.
* **FR-2.2:** Scoped Microsoft Graph API permissions (`offline_access`, `User.Read`, `Mail.Read`, `Mail.ReadWrite`, `Mail.Send`).
* **FR-2.3:** Synchronous and background polling of incoming Outlook messages with multi-provider inbox normalization.
* **FR-2.4:** Seamless reply dispatching via Microsoft Graph API reply endpoints with conversation threading.

### 3.3 Feature 3: Automated Email Processing & Smart Labeling
* **FR-3.1:** Background email fetch via periodic cron / background worker (Celery + Redis).
* **FR-3.2:** Classification of incoming emails into predefined categories:
  * 📥 `New Application`
  * ❓ `Candidate Query`
  * 🔄 `Follow-up`
  * 📅 `Interview Response`
  * 🚫 `Rejection / Unsuitable`
  * 📁 `Other`
* **FR-3.3:** Automatic application of inbox visual cues and database categorization across all connected providers.

### 3.4 Feature 4: Resume Parsing & Candidate Data Extraction
* **FR-4.1:** Automated extraction of attached candidate files (`.pdf`, `.docx`).
* **FR-4.2:** Text extraction from attachments using `pypdf` and `python-docx`.
* **FR-4.3:** Structured parsing of candidate metadata (Name, Email, Skills, Experience, Portfolio Links) stored in Supabase PostgreSQL database.

### 3.5 Feature 5: Human-in-the-Loop AI Draft Generation & Approval Queue
* **FR-5.1:** AI-driven personalized draft generation using Groq LLM (Llama 3 / Mixtral) tailored to candidate resume details and context.
* **FR-5.2:** Pending Draft Queue where recruiters view AI generated response side-by-side with email history and candidate details.
* **FR-5.3:** One-Click Actions:
  * **Approve & Send:** Immediately dispatches the draft via Gmail API or Microsoft Graph API based on origin.
  * **Edit & Send:** Recruiter edits draft inline before sending.
  * **Reject Draft:** Discards the AI draft.

### 3.6 Feature 6: Hybrid RAG HR Inbox Assistant
* **FR-6.1:** Hybrid search query handler supporting both structured data lookups and semantic vector queries.
* **FR-6.2:** Structured queries: Answers quantitative inbox questions directly via SQL (e.g., *"How many emails did I receive today?"*, *"How many pending drafts do I have?"*).
* **FR-6.3:** Semantic search: Embeds email text using vector embeddings (`vecs` / pgvector) and performs RAG generation via Groq LLM (e.g., *"Do we have any candidates with Python experience?"*).
* **FR-6.4:** Chat history persistence in Supabase `chat_messages` table.

---

## 🏗️ 4. Technical Architecture

```
                                  +-------------------+
                                  |   React Frontend  |
                                  +---------+---------+
                                            |
                                     REST API (FastAPI)
                                            |
                  +-------------------------+-------------------------+
                  |                                                   |
        +---------v---------+                               +---------v---------+
        |  FastAPI Backend  |                               |   Celery Worker   |
        |   (App Router)    |                               |  (Redis Task Q)   |
        +----+---------+----+                               +----+---------+----+
             |         |                                         |         |
      Google / MS   Groq LLM                                Gmail/MS Graph  RAG Embedder
      OAuth Flow       |                                         |         |
             +---------+--------------------+--------------------+---------+
                                            |
                                   +--------v--------+
                                   | Supabase DB     |
                                   | (PG + pgvector) |
                                   +-----------------+
```

### 4.1 System Components
1. **API Web Server (FastAPI):** Exposes RESTful endpoints for Auth, Gmail & Outlook Sync, Email management, Draft approval, and RAG Chat.
2. **Background Queue (Redis + Celery):** Asynchronous execution of heavy tasks (fetching emails, parsing resumes, generating vector embeddings, generating LLM drafts).
3. **Database Layer (Supabase / PostgreSQL):** Relational storage for users, emails, candidates, drafts, and pgvector extension for dense vector embeddings.
4. **AI & RAG Pipeline (LangChain + Groq):** Orchestrates context building, prompt engineering, vector searching, and draft/chat generation.

---

## 📊 5. Database Schema & Data Models

### 5.1 Entities Summary
* `users`: Stores user profile, OAuth credentials (encrypted), preferences.
* `gmail_connections`: User's connected Google Gmail accounts and synchronization state.
* `outlook_connections`: User's connected Microsoft Outlook / 365 accounts and token state.
* `emails`: Email metadata, body text, category label, thread ID, provider (`gmail`/`outlook`), sender info.
* `candidate_applications`: Parsed candidate metadata, CV content, skill tags, matched job ID.
* `drafts`: Generated draft responses, approval status (`pending`, `approved`, `sent`, `rejected`), suggested response type.
* `chat_messages`: HR RAG chat history, natural language queries, LLM answers, source citations.

---

## ⏱️ 6. Non-Functional Requirements (NFRs)

* **Performance:**
  * Gmail label synchronization completed in < 3 seconds per email.
  * AI draft generation latency < 4 seconds per email.
  * Hybrid RAG query response time < 2.5 seconds.
* **Security & Privacy:**
  * Strict compliance with Google API User Data Policy.
  * Encrypted storage of refresh tokens via AES-256.
  * All communication enforced over HTTPS / TLS 1.3.
* **Reliability & Scalability:**
  * Celery retry policies for rate-limited Gmail API calls.
  * Support for up to 5,000 processed emails/day per user.

---

## 📈 7. Success Metrics & Key Performance Indicators (KPIs)

1. **Candidate Response Time:** Reduction in average response time from **48 hours to < 1 hour**.
2. **Time Saved per Recruiter:** Minimum **2 hours saved per recruiter per day** on administrative inbox work.
3. **Draft Acceptance Rate:** **> 85%** of AI-generated response drafts accepted and sent without manual modification.
4. **Candidate Ghosting Rate:** **0% unhandled application emails** after 48 hours of receipt.

---

## 🛣️ 8. Roadmap & Future Scope

* **Phase 1 (Completed):** Google OAuth, Gmail Integration, Automated Email Labeling, Celery Async Worker, AI Draft Generation & Approval Queue, RAG Chat.
* **Phase 2 (Upcoming):**
  * Automated Calendly / Google Calendar interview scheduling integration.
  * Custom recruiter tone tuning (formal, startup friendly, technical).
  * Multi-recruiter team workspace with role-based access control (RBAC).
  * ATS export sync (Greenhouse, Lever, Notion workspace export).
