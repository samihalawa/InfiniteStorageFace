# InfiniteStorageFace.py
# !pip install gradio huggingface_hub plyer rich


import os
import gradio as gr
from huggingface_hub import HfApi, upload_folder, create_repo, login
from threading import Thread, Event, Lock
import queue
from plyer import notification  # For desktop notifications
from rich.console import Console
import re

# Initialize Rich console for logging
console = Console()

# Initialize Hugging Face API client
api = HfApi()

# Queue for logging messages
log_queue = queue.Queue()

# Event to signal upload cancellation
cancel_event = Event()

# Lock for thread-safe operations
upload_lock = Lock()

# Regular expression for validating repository ID
REPO_ID_REGEX = re.compile(r"^[a-zA-Z0-9\-_.]+/[a-zA-Z0-9\-_.]+$")

# Prefilled sample values
SAMPLE_TOKEN = "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"
SAMPLE_FOLDER_PATH = "/users/sami/Documents/Megacursos/MEGACURSOS_S3_MASTER/angular"
SAMPLE_REPO_ID = "luigi12345/megacursos2"
SAMPLE_THREADS = 5

# Shared log list
shared_logs = []

# Function to send desktop notifications
def send_notification(title, message, timeout=5):
    try:
        notification.notify(title=title, message=message, timeout=timeout)
    except Exception as e:
        console.log(f"❌ Failed to send notification: {e}")

# Function to log messages and send notifications
def log(message):
    log_queue.put(message)
    shared_logs.append(message)
    console.log(message)
    if "✅" in message:
        send_notification("InfiniteStorageFace", message, timeout=5)
    elif "❌" in message:
        send_notification("InfiniteStorageFace - Error", message, timeout=5)
    elif "🚀" in message:
        send_notification("InfiniteStorageFace", message, timeout=3)

# Function to authenticate user with Hugging Face token
def authenticate(token):
    if not token:
        log("❌ Hugging Face Token is required.")
        return False, "❌ Hugging Face Token is required."
    try:
        login(token)  # Authenticate user
        log("✅ Authenticated successfully!")
        return True, "✅ Authenticated successfully!"
    except Exception as e:
        log(f"❌ Authentication failed: {e}")
        return False, f"❌ Authentication failed: {e}"

# Function to validate repository ID format
def validate_repo_id(repo_id):
    if not repo_id:
        log("❌ Repository ID is required.")
        return False, "❌ Repository ID is required."
    if not REPO_ID_REGEX.match(repo_id):
        log("❌ Repository ID must be in the format 'username/repo-name'.")
        return False, "❌ Repository ID must be in the format 'username/repo-name'."
    return True, "✅ Repository ID format is valid."

# Function to create repository if it doesn't exist
def create_repo_if_not_exists(repo_id, token, repo_type="space", space_sdk="static", private=False):
    try:
        api.create_repo(repo_id=repo_id, token=token, repo_type=repo_type, space_sdk=space_sdk, private=private, exist_ok=True)
        log(f"✅ Created new repository: '{repo_id}'.")
        return True, f"✅ Created new repository: '{repo_id}'."
    except Exception as create_err:
        log(f"❌ Failed to create repository '{repo_id}': {create_err}")
        return False, f"❌ Failed to create repository '{repo_id}': {create_err}"
        
# Function to upload files to Hugging Face repository
def upload_files(folder_path, repo_id, token, private=False, threads=5):
    if cancel_event.is_set():
        log("❌ Upload has been cancelled.")
        return "❌ Upload has been cancelled."

    if not folder_path:
        log("❌ Folder Path is required.")
        return "❌ Folder Path is required."
    if not os.path.isdir(folder_path):
        log(f"❌ The folder path '{folder_path}' does not exist.")
        return f"❌ The folder path '{folder_path}' does not exist."
    if not repo_id:
        log("❌ Repository ID is required.")
        return "❌ Repository ID is required."
    if not validate_repo_id(repo_id)[0]:
        return validate_repo_id(repo_id)[1]
    if not token:
        log("❌ Hugging Face Token is required.")
        return "❌ Hugging Face Token is required."

    def upload_process():
        with upload_lock:
            try:
                # Step 1: Authenticate
                success, auth_message = authenticate(token)
                if not success:
                    return

                # Step 2: Create repository if it doesn't exist
                success, creation_message = create_repo_if_not_exists(repo_id, token, repo_type="space", private=private)
                if not success:
                    return

                # Step 3: Initialize upload parameters
                upload_params = {
                    "folder_path": folder_path,
                    "repo_id": repo_id,
                    "repo_type": "space",
                    "token": token,
                    "ignore_patterns": ["**/.git/**", "**/.DS_Store", "**/logs/*.txt"],
                    "multi_commits": True,
                    "multi_commits_verbose": True
                }

                # Step 4: Start upload
                log("🚀 Starting upload process...")
                try:
                    upload_folder(**upload_params)
                    log("✅ Upload completed successfully!")
                except Exception as upload_err:
                    log(f"❌ Upload failed: {upload_err}")
            except Exception as e:
                log(f"❌ An unexpected error occurred during upload: {e}")

    # Start the upload process in a separate thread to keep the UI responsive
    upload_thread = Thread(target=upload_process, daemon=True)
    upload_thread.start()

    return "🚀 Upload initiated. Check the logs for progress."

# Function to update logs in the Gradio interface
def update_logs():
    return "\n".join(shared_logs)

# Function to cancel the upload
def cancel_upload():
    cancel_event.set()
    log("❓ Cancel requested. Upload may not stop immediately.")

# Gradio Interface
def create_interface():
    with gr.Blocks() as app:
        gr.Markdown("# 🚀 InfiniteStorageFace")
        gr.Markdown("**Effortlessly upload your files to Hugging Face Spaces with real-time feedback and progress tracking!**")

        token = gr.Textbox(
            label="Hugging Face Token",
            type="password",
            placeholder="Enter your Hugging Face API token",
            value=SAMPLE_TOKEN,
            interactive=True,
        )
        
        private = gr.Checkbox(
            label="Make Repository Private",
            value=False,
            interactive=True,
        )

        folder_path = gr.Textbox(
            label="Folder Path to Upload",
            placeholder="Enter the absolute path to your folder",
            value=SAMPLE_FOLDER_PATH,
            interactive=True,
            lines=1,
        )

        repo_id = gr.Textbox(
            label="Repository ID",
            placeholder="e.g., your-username/your-repo",
            value=SAMPLE_REPO_ID,
            interactive=True,
            lines=1,
        )

        threads = gr.Slider(
            label="Number of Threads",
            minimum=1,
            maximum=20,
            step=1,
            value=SAMPLE_THREADS,
            interactive=True,
        )

        upload_button = gr.Button(
            "Start Upload",
            variant="primary",
            interactive=True,
        )

        upload_button.click(
            fn=upload_files,
            inputs=[folder_path, repo_id, token, private, threads],
            outputs=gr.Textbox(label="Upload Status")
        )

        log_output = gr.Textbox(
            label="Upload Logs",
            lines=20,
            interactive=False,
            placeholder="Logs will appear here..."
        )

        log_refresh = gr.Button(
            "Refresh Logs",
            interactive=True,
        )

        log_refresh.click(
            fn=update_logs,
            inputs=None,
            outputs=log_output
        )

        gr.Markdown("""
        ---
        **Instructions**:
        1. **Hugging Face Token**: Obtain your API token from your [Hugging Face account settings](https://huggingface.co/settings/tokens).
        2. **Folder Path**: Specify the absolute path to the folder you want to upload.
        3. **Repository ID**: Enter the desired repository name in the format `username/repo-name`. Leave blank to create a new repository automatically.
        4. **Number of Threads**: Adjust the number of threads to optimize upload speed based on your internet connection.
        5. **Start Upload**: Click to begin uploading your files. Monitor progress in the Logs area.
        6. **Cancel Upload**: Click to cancel the ongoing upload if needed.
        """)

    return app

# Launch the Gradio app
app = create_interface()
app.launch()
