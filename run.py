"""Convenience launcher: `python run.py` starts uvicorn on :8010."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8010, reload=False)
