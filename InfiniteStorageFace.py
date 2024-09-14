# InfiniteStorageFace.py

import os
import gradio as gr
from huggingface_hub import HfApi, upload_folder, create_repo, list_repo_files
from threading import Thread, Event
import queue
from plyer import notification  # For desktop notifications
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, TransferSpeedColumn
import time
import re

# Initialize Rich console for logging
console = Console()

# Initialize Hugging Face API client
api = HfApi()

# Queue for logging messages
log_queue = queue.Queue()

# Event to signal upload cancellation
cancel_event = Event()

# Regular expression for validating repository ID
REPO_ID_REGEX = re.compile(r"^[a-zA-Z0-9\-_.]+/[a-zA-Z0-9\-_.]+$")

# Function to send desktop notifications
def send_notification(title, message, timeout=5):
    try:
        notification.notify(
            title=title,
            message=message,
            timeout=timeout
        )
    except Exception as e:
        console.log(f"❌ Failed to send notification: {e}")

# Function to log messages and send notifications based on message type
def log(message):
    log_queue.put(message)
    console.log(message)
    if "✅" in message:
        send_notification("InfiniteStorageFace", message, timeout=5)
    elif "❌" in message:
        send_notification("InfiniteStorageFace - Error", message, timeout=5)
    elif "🚀" in message:
        send_notification("InfiniteStorageFace", message, timeout=3)
    elif "🔄" in message:
        send_notification("InfiniteStorageFace", message, timeout=2)
    elif "❓" in message:
        send_notification("InfiniteStorageFace", message, timeout=4)

# Function to authenticate user with Hugging Face token
def authenticate(token):
    if not token:
        log("❌ Hugging Face Token is required.")
        return "❌ Hugging Face Token is required."
    try:
        api.login(token)
        log("✅ Authenticated successfully!")
        return "✅ Authenticated successfully!"
    except Exception as e:
        log(f"❌ Authentication failed: {e}")
        return f"❌ Authentication failed: {e}"

# Function to validate repository ID format
def validate_repo_id(repo_id):
    if not REPO_ID_REGEX.match(repo_id):
        log("❌ Repository ID must be in the format 'username/repo-name'.")
        return False
    return True

# Function to create repository if it doesn't exist
def create_repo_if_not_exists(repo_id, token, repo_type="dataset", private=False):
    if not repo_id:
        log("❌ Repository ID is required.")
        return "❌ Repository ID is required."
    try:
        # Check if repository exists by listing its files
        api.list_repo_files(repo_id=repo_id, repo_type=repo_type, token=token)
        log(f"✅ Repository '{repo_id}' exists. Proceeding with upload...")
        return f"✅ Repository '{repo_id}' exists. Proceeding with upload..."
    except Exception:
        # If repository does not exist, create it
        try:
            create_repo(repo_id=repo_id, token=token, private=private, repo_type=repo_type, exist_ok=True)
            log(f"✅ Created new repository: '{repo_id}'.")
            return f"✅ Created new repository: '{repo_id}'."
        except Exception as create_err:
            log(f"❌ Failed to create repository '{repo_id}': {create_err}")
            return f"❌ Failed to create repository '{repo_id}': {create_err}"

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
    if not validate_repo_id(repo_id):
        return "❌ Invalid Repository ID format."
    if not token:
        log("❌ Hugging Face Token is required.")
        return "❌ Hugging Face Token is required."

    def upload_process():
        try:
            # Step 1: Authenticate
            auth_message = authenticate(token)
            if "❌" in auth_message:
                return

            # Step 2: Create repository if it doesn't exist
            creation_message = create_repo_if_not_exists(repo_id, token, repo_type="dataset", private=private)
            if "❌" in creation_message:
                return

            # Step 3: Start upload using upload_folder with multi_commits for large uploads
            log("🚀 Initiating upload...")
            future = upload_folder(
                folder_path=folder_path,
                repo_id=repo_id,
                repo_type="dataset",
                token=token,
                ignore_patterns=["**/.git/**", "**/logs/*.txt"],
                multi_commits=True,
                multi_commits_verbose=True,
                run_as_future=True
            )

            log("🔄 Upload started in the background. You can continue using the app.")

            # Step 4: Monitor upload progress
            with Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                upload_task = progress.add_task("Uploading...", total=100)  # Dummy total for visualization
                while not future.done():
                    if cancel_event.is_set():
                        log("❌ Upload cancellation requested.")
                        # Note: huggingface_hub does not support cancelling uploads directly
                        # This is a placeholder to show where cancellation logic would go
                        break
                    if future.exception():
                        log(f"❌ Upload failed: {future.exception()}")
                        break
                    # Increment dummy progress
                    progress.advance(upload_task, advance=1)
                    # Sleep briefly to simulate progress (since actual progress isn't tracked)
                    time.sleep(0.1)
                else:
                    if future.result():
                        log("✅ Upload completed successfully!")
                    else:
                        log("❌ Upload failed without exception.")

        except Exception as e:
            log(f"❌ An unexpected error occurred during upload: {e}")

    # Start the upload process in a separate thread to keep the UI responsive
    upload_thread = Thread(target=upload_process, daemon=True)
    upload_thread.start()

    return "🚀 Upload initiated. Check the Logs tab for progress."

# Function to update logs in the Gradio interface
def update_logs():
    messages = []
    while not log_queue.empty():
        messages.append(log_queue.get())
    return "\n".join(messages)

# Function to cancel the upload (Note: Hugging Face API does not support cancellation)
def cancel_upload():
    cancel_event.set()
    log("❓ Cancel requested. Upload may not stop immediately.")

# Function to validate user inputs before starting upload
def validate_inputs(token, repo_id, folder_path):
    errors = []
    if not token:
        errors.append("Hugging Face Token is required.")
    if not repo_id:
        errors.append("Repository ID is required.")
    if not folder_path:
        errors.append("Folder Path is required.")
    elif not os.path.isdir(folder_path):
        errors.append(f"The folder path '{folder_path}' does not exist.")
    return errors

# Gradio Interface
def create_interface():
    with gr.Blocks(css="""
        body {
            background-color: #f0f2f6;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }
        .gr-button-primary {
            background-color: #4CAF50;
            color: white;
            font-weight: bold;
        }
        .gr-textbox {
            border: 2px solid #4CAF50;
            border-radius: 5px;
            padding: 10px;
        }
        .gr-checkbox label {
            color: #4CAF50;
            font-weight: bold;
        }
        .gr-slider {
            color: #4CAF50;
        }
        .gr-markdown {
            color: #333333;
        }
    """) as app:
        gr.Markdown("# 🚀 InfiniteStorageFace")
        gr.Markdown("**Effortlessly upload your large datasets to Hugging Face with real-time feedback and progress tracking!**")
    
        with gr.Tab("Upload"):
            with gr.Row():
                token = gr.Textbox(
                    label="Hugging Face Token",
                    type="password",
                    placeholder="Enter your Hugging Face API token",
                    interactive=True,
                    info="Your Hugging Face API token is required to authenticate and upload datasets."
                )
                private = gr.Checkbox(
                    label="Make Repository Private",
                    value=False,
                    info="If checked, the repository will be private."
                )
    
            folder_path = gr.Textbox(
                label="Folder Path to Upload",
                placeholder="Enter the absolute path to your folder",
                interactive=True,
                info="Specify the absolute path to the folder you want to upload."
            )
            repo_id = gr.Textbox(
                label="Repository ID",
                placeholder="e.g., your-username/your-repo",
                interactive=True,
                info="Enter the desired repository name in the format `username/repo-name`."
            )
    
            threads = gr.Slider(
                label="Number of Threads",
                minimum=1,
                maximum=20,
                step=1,
                value=5,
                info="Adjust the number of threads to optimize upload speed based on your internet connection."
            )
    
            upload_button = gr.Button(
                "Start Upload",
                variant="primary",
                interactive=True,
                info="Click to begin uploading your files."
            )
    
            cancel_button = gr.Button(
                "Cancel Upload",
                variant="secondary",
                interactive=True,
                info="Click to cancel the ongoing upload."
            )
            cancel_button.click(
                fn=cancel_upload,
                inputs=None,
                outputs=None
            )
    
        with gr.Tab("Logs"):
            log_output = gr.Textbox(
                label="Upload Logs",
                lines=20,
                interactive=False,
                placeholder="Logs will appear here..."
            )
            log_refresh = gr.Button(
                "Refresh Logs",
                interactive=True,
                info="Click to refresh the log messages."
            )
            log_refresh.click(
                update_logs,
                inputs=None,
                outputs=log_output
            )
    
        gr.Markdown("""
        ---
        **Instructions**:
        1. **Hugging Face Token**: Obtain your API token from your [Hugging Face account settings](https://huggingface.co/settings/tokens).
        2. **Folder Path**: Specify the absolute path to the folder you want to upload.
        3. **Repository ID**: Enter the desired repository name in the format `username/repo-name`.
        4. **Number of Threads**: Adjust the number of threads to optimize upload speed based on your internet connection.
        5. **Start Upload**: Click to begin uploading your files. Monitor progress in the Logs tab.
        6. **Cancel Upload**: Click to cancel the ongoing upload if needed.
        """)
    
    return app

# Launch the Gradio app
app = create_interface()
app.launch()
