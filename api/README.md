# Skills Mapping Recommendation API

## Overview

This fastapi backend exposes a `/ranking` endpoint that accepts a resume PDF or pasted text and returns ranked course recommendations from the repo's course catalog.

## Setup

1. Create and activate a Python virtual environment.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

2. Run the server:

```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

3. Open `http://localhost:8000/docs` to explore the API.

## Usage

Send a `multipart/form-data` request to `/ranking` with either:
- `resume_text` containing pasted resume content
- `resume_file` containing a `.pdf` or `.txt` file

Optional form fields:
- `user_level` (`beginner`, `intermediate`, `advanced`)
- `target_pathways` (comma-separated string)
- `top_n` (number of recommendations)
