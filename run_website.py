"""
SortDesk Website & Server Launcher
Runs the complete SortDesk web application on http://localhost:8000
"""
import sys
import uvicorn

if __name__ == "__main__":
    print("=" * 70)
    print("  🦋 SORTDESK — THE FAIR FIRST-ROUND RECRUITER")
    print("  Serving web dashboard at: http://localhost:8000/")
    print("  Swagger API documentation at: http://localhost:8000/docs")
    print("=" * 70)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
