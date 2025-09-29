# EduAssist-AI-BE
Backed application for Education assistance mainly to help summarize video Lectures, Slides and Docs 


## Installation

To set up the project, follow these steps:

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/EduAssist-AI-BE.git
    cd EduAssist-AI-BE
    ```
    (Note: Replace `https://github.com/your-username/EduAssist-AI-BE.git` with the actual repository URL if different.)

2.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    ```

3.  **Activate the virtual environment:**
    *   **On Windows:**
        ```bash
        .\venv\Scripts\activate
        ```
    *   **On macOS/Linux:**
        ```bash
        source venv/bin/activate
        ```

4.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Running the Application

To run the application, execute the following command:

```bash
uvicorn app.main:app --reload --port 8000 --host 127.0.0.1
```
