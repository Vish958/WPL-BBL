"""Light wrapper entrypoint expected by the deployment/runtime.
This executes the existing `main-app.py` which contains the Streamlit app.
"""
import runpy

if __name__ == "__main__":
    runpy.run_path("main-app.py", run_name="__main__")
