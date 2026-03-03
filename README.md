# 💬📁 ZapShare — Chat & Sharing Platform

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi)
![Supabase](https://img.shields.io/badge/Supabase-Database-3ECF8E?logo=supabase)
![Status](https://img.shields.io/badge/Project-Active-success)

> 🚀 A modern cloud-based real-time chat & file sharing platform designed for scalability and future offline capabilities

---

## ✨ Overview

**ZapShare** is a full-stack communication platform that combines:

- 💬 Real-time messaging  
- 📁 Secure file sharing  
- 👤 User authentication  
- ☁️ Cloud deployment  

The system is designed with a modular architecture to support future enhancements such as LAN/offline communication and high-performance modules.

---

## 🎯 Key Features

### 👤 User System
- Secure registration & login
- Profile management
- Online/offline status

### 💬 Chat
- Real-time one-to-one messaging
- Message history
- Text & file messages

### 📁 File Sharing
- Upload & download files
- Share files directly in chat
- File metadata storage

---

## 🏗 System Architecture

Frontend (Web UI)  
⬇  
FastAPI Backend  
⬇  
Supabase (PostgreSQL + Storage)

---

## 🛠 Tech Stack

**Backend**
- FastAPI (Python)
- WebSockets for real-time communication

**Database & Storage**
- Supabase (PostgreSQL)
- Supabase Storage

**Frontend**
- HTML, CSS, JavaScript  
- React (planned)

**Deployment**
- Free-tier cloud platform

---

## 📂 Project Structure

```
zapshare/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── routes/
│   │   ├── models/
│   │   └── websocket/
│
├── frontend/
├── uploads/
└── README.md
```

---

## 🚀 Getting Started

### Prerequisites

```
Python 3.10+
uv package manager
Git
```

---

### Installation

```
git clone https://github.com/your-username/zapshare.git
cd zapshare
```

### Create Virtual Environment

```
uv venv
```

### Activate Virtual Environment (Windows)

```
.venv\Scripts\activate
```

### Install Dependencies

```
uv pip install -r requirements.txt
```

### Run Server

```
uvicorn app.main:app --reload
```

### Open in Browser

```
http://127.0.0.1:8000/docs
```

---

## 🗄 Database Setup

```
1. Create a Supabase project
2. Configure database tables
3. Add API keys as environment variables
```

---

## 🛣 Roadmap

### Phase 1 — Cloud Chat Platform (In Progress)
- [ ] User authentication
- [ ] Chat system
- [ ] File sharing

### Phase 2 — Performance & Scaling
- [ ] Go-based microservices
- [ ] Optimized file transfer

### Phase 3 — Offline & LAN Mode
- [ ] Peer-to-peer communication
- [ ] Local network discovery

### Phase 4 — Desktop Application
- [ ] Wails-based app
- [ ] Cross-platform support

---

## 🎓 Educational Purpose

This project demonstrates:

- Full-stack development  
- Real-time systems  
- Cloud deployment  
- System design  
- Scalable architecture  

---

## 👨‍💻 Author

Ajinkya Shelke

Built as a final-year BCA project with future real-world scalability in mind.

---

⭐ If you like this project, give it a star!