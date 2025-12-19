# Contributing to Nesta Signal Scout

Thank you for your interest in contributing to **Nesta Signal Scout**! We welcome contributions that help us improve our horizon scanning capabilities, whether it's refining the AI agent's logic, enhancing the UI, or fixing bugs.

This document outlines the standards and steps for contributing to this project.

## 📋 Prerequisites

Before you begin, ensure you have the following keys and accounts. You will need these to run the backend locally:

1.  **OpenAI API Key**: Access to `gpt-4.1-mini` (or standard `gpt-4o-mini`).
2.  **Google Custom Search JSON API**: An API Key and Search Engine ID (CX).
3.  **Google Cloud Service Account**: A JSON key file for accessing Google Sheets.
4.  **Python 3.9+**: Installed on your machine.

## 🚀 Setting Up Your Development Environment

### 1. Fork and Clone
  
  - Fork the repository to your GitHub account and clone it locally:
  ```bash
  git clone [https://github.com/YOUR-USERNAME/nesta-signal-scout.git](https://github.com/YOUR-USERNAME/nesta-signal-scout.git)
  cd nesta-signal-scout
  ```
### 2. Backend Setup ("The Brain")

  - Create a Virtual Environment:
  ```bash
  python -m venv venv
  source venv/bin/activate  # On Windows: venv\Scripts\activate
  ```

  - Install Dependencies:
  ```bash
  pip install -r requirements.txt
  ```

  - Configure Environment Variables: Create a .env file in the root directory. Do not commit this file.
  ```Ini, TOML
  OPENAI_API_KEY=your_key_here
  ASSISTANT_ID=your_assistant_id

  # Google Search
  Google_Search_API_KEY=your_google_key
  Google_Search_CX=your_cx_id
  
  # Google Sheets
  SHEET_ID=your_test_sheet_id
  SHEET_URL=[https://docs.google.com/](https://docs.google.com/)...
  GOOGLE_CREDENTIALS={"type": "service_account", ...} # Full JSON string
  ```
  > Tip: For local development, use a separate "Test" Google Sheet ID to avoid corrupting the production database.

  Run the Server:
  ```bash
  uvicorn main:app --reload
  ```
  The backend will start at http://127.0.0.1:8000.

### 3. Frontend Setup ("The Face")

  The frontend is Vanilla HTML/JS using Tailwind CSS via CDN. No Node.js build step is required.

  - Open index.html in your editor.

  - Ensure the API_BASE_URL inside the <script> tag is pointing to your local backend:
  ```JavaScript
  const API_BASE_URL = (window.location.hostname === 'localhost') 
    ? '[http://127.0.0.1:8000](http://127.0.0.1:8000)' 
    : '[https://nesta-signal-backend.onrender.com](https://nesta-signal-backend.onrender.com)';  ```
  ```

  - Open index.html in your browser. You can simply double-click the file, or serve it using Python for a better experience:
   ```bash
  python -m http.server 5500
  ```

### 💻 Development Guidelines
Backend (Python)
- The Friction Method: If you modify the prompt logic in main.py, ensure the agent maintains its "skeptical" persona. It must verify signals via fetch_article_text before displaying them.

- Error Handling: Ensure any new external API calls (e.g., to GTR or Google) have try/except blocks to prevent the agent from crashing mid-scan.

- Type Hinting: Please use Python type hints where possible (e.g., def my_func(url: str) -> bool:).

Frontend (HTML/CSS)
- Nesta Branding: We strictly adhere to the Nesta Visual Identity.

  - Fonts: Use Zosia Display for headings and Averta for body text.

  - Colours: Use the defined Tailwind config colors (nesta-blue, nesta-navy, nesta-pink, etc.). Do not introduce random hex codes.

- Simplicity: Do not introduce heavy frontend frameworks (React, Vue) without a major architectural discussion. The goal is to keep the frontend portable (GitHub Pages compatible).

Database (Google Sheets)
- Schema Consistency: If you add new fields to the signal object, update the ensure_sheet_headers function in main.py to prevent header mismatches.


### 📬 Submitting a Pull Request
- Create a Branch: Use a descriptive name (e.g., feature/add-gtr-source or fix/mobile-menu).

- Test Locally: Verify that the "Initiate Scan" flow completes successfully and data is written to your test Google Sheet.

- Commit Messages: Write clear, concise commit messages.

- Push and Open PR: Push to your fork and open a Pull Request against the main branch.

- Description: In your PR description, explain what you changed and why. If you changed the UI, please include a screenshot.


### 🤝 Code of Conduct
Please be respectful and constructive in all interactions. We are building a tool to help discover the future—let's build it with a positive, collaborative spirit.
