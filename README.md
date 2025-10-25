# EECE-351-AUBus-Project

## Overview
AUBus is a **carpooling service** among AUB students developed as part of the EECE 351 – Computing Networks and Services course.  
It connects student **drivers** with **passengers** based on their location and commuting schedule, using a **Python-based client-server system** with a GUI and database integration.

### Key Features
- User registration and login (server-authenticated)
- Schedule management and ride requests
- Peer-to-peer chat between drivers and passengers
- Driver/passenger rating system
- Weather information via public API *(bonus feature)*
- Hybrid architecture: Client-Server + P2P communication
- TCP transport protocol with multithreading

---

## Project Structure
```

client/      → PyQt5 GUI and client logic
server/      → Server-side logic and database integration
protocol/    → Message formatting, encoding/decoding (JSON)
db/          → SQLite database and schema
tests/       → Unit and integration tests
assets/      → Icons, UI files, or reference media

````

---

## Virtual Environment Setup

```bash
python -m venv .venv
source .venv/bin/activate     # (Linux/macOS)
.\.venv\Scripts\Activate.ps1  # (Windows)

pip install -r requirements.txt
````

---

## How to Run

1. Start the server:

   ```bash
   cd server
   python server_main.py
   ```

2. Start the client:

   ```bash
   cd client
   python client_main.py
   ```

3. Use the GUI to register, log in, and send ride requests.


---

## Team Information

Hayam Itani (hoi01@mail.aub.edu)
Mohammad Jaffal (mgj08@mail.aub.edu)
Sarah Bayrakdar (sib10@mail.aub.edu)

---

