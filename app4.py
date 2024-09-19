# InfiniteStorageFace.py
# Requirements: pip install gradio huggingface_hub rich python-dotenv

import os
import gradio as gr
from huggingface_hub import (
    HfApi,
    upload_folder,
    create_repo,
    login,
    list_repo_files,
)
from threading import Thread, Event, Lock
import queue
from rich.console import Console
from rich.logging import RichHandler
import re
import time
import dotenv
import logging

# Load environment variables
dotenv.load_dotenv()

# Default values
DEFAULT_REPO = os.getenv("DEFAULT_REPO", "luigi12345/megacursos1")
DEFAULT_LOCAL_PATH = os.getenv("DEFAULT_LOCAL_PATH", "/Users/samihalawa/git/BACKUP_IMAGES-main")

# Initialize Rich console for logging
console = Console()

# Setup logging with Rich
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%Y-%m-%d %H:%M:%S]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)]
)
logger = logging.getLogger("InfiniteStorageFace")

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

# Prefilled sample values (Replace with secure methods in production)
SAMPLE_TOKEN = "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"
SAMPLE_REPO_ID = DEFAULT_REPO
SAMPLE_FOLDER_PATH = DEFAULT_LOCAL_PATH
SAMPLE_THREADS = 5

# Shared log list
shared_logs = []

# Function to log messages
def log(message):
    timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]")
    full_message = f"{timestamp} {message}"
    log_queue.put(full_message)
    shared_logs.append(full_message)
    logger.info(message)

# Function to authenticate user with Hugging Face token
def authenticate(token):
    if not token:
        log("❌ Hugging Face Token is required.")
        return False, "❌ Hugging Face Token is required."
    try:
        login(token)
        log("✅ Authenticated successfully!")
        return True, "✅ Authenticated successfully!"
    except Exception as e:
        log(f"❌ Authentication failed: {e}")
        return False, f"❌ Authentication failed: {e}"

# Function to validate repository ID format
def validate_repo_id(repo_id):
    if not repo_id or not REPO_ID_REGEX.match(repo_id):
        log("❌ Repository ID must be in the format 'username/repo-name'.")
        return False, "❌ Repository ID must be in the format 'username/repo-name'."
    return True, "✅ Repository ID format is valid."

# Function to create repository if it doesn't exist
def create_repo_if_not_exists(repo_id, token, repo_type="space", private=False):
    try:
        api.list_repo_files(repo_id=repo_id, repo_type=repo_type, token=token)
        log(f"✅ Repository '{repo_id}' exists. Proceeding with upload...")
        return True, f"✅ Repository '{repo_id}' exists. Proceeding with upload..."
    except Exception:
        log(f"❌ Repository '{repo_id}' does not exist, creating it...")
        try:
            create_repo(
                repo_id=repo_id,
                token=token,
                private=private,
                repo_type=repo_type,
                exist_ok=True,
                space_sdk="static"
            )
            log(f"✅ Created new repository: '{repo_id}'.")
            return True, f"✅ Created new repository: '{repo_id}'."
        except Exception as create_err:
            log(f"❌ Failed to create repository '{repo_id}': {create_err}")
            return False, f"❌ Failed to create repository '{repo_id}': {create_err}"

# Function to check if there are files to upload after applying ignore patterns
def has_files_to_upload(folder_path, ignore_patterns):
    for root, dirs, files in os.walk(folder_path):
        # Apply ignore patterns to directories
        dirs[:] = [d for d in dirs if not any(re.match(pattern.replace("**/", ""), os.path.relpath(os.path.join(root, d), folder_path) + "/") for pattern in ignore_patterns)]
        # Check if any files are left after applying ignore patterns
        for file in files:
            relative_path = os.path.relpath(os.path.join(root, file), folder_path)
            if not any(re.match(pattern.replace("**/", ""), relative_path) for pattern in ignore_patterns):
                return True
    return False

# Function to check for sensitive data
def contains_sensitive_data(folder_path):
    sensitive_keywords = ["API_KEY", "SECRET", "TOKEN"]
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            with open(os.path.join(root, file), 'r') as f:
                content = f.read()
                if any(keyword in content for keyword in sensitive_keywords):
                    return True
    return False

# Function to upload a single folder
def upload_single_folder(folder_path, repo_id, token, repo_type, private, path_in_repo):
    # Define minimal ignore patterns
    ignore_patterns = [
        "**/.DS_Store",
    ]

    # Validate repository ID format
    if not validate_repo_id(repo_id)[0]:
        log("❌ Invalid repository ID format. Upload aborted.")
        return

    # Check if the folder exists
    if not os.path.isdir(folder_path):
        log(f"❌ The folder path '{folder_path}' does not exist.")
        return

    # Check if there are files to upload
    if not has_files_to_upload(folder_path, ignore_patterns):
        log(f"⚠️ No files to upload in '{folder_path}' after applying ignore patterns. Skipping...")
        return

    upload_params = {
        "folder_path": folder_path,
        "repo_id": repo_id,  # Correct repo_id without subfolders
        "repo_type": repo_type,
        "token": token,
        "path_in_repo": path_in_repo,  # Specify target path in repo
        "ignore_patterns": ignore_patterns,
        "multi_commits": True,
        "multi_commits_verbose": True,
    }

    log(f"🚀 Uploading folder '{folder_path}' to '{path_in_repo}' in repository '{repo_id}'...")
    try:
        upload_folder(**upload_params)
        log(f"✅ Upload completed for '{folder_path}'!")
    except Exception as upload_err:
        log(f"❌ Upload failed for '{folder_path}': {upload_err}")

# Function to upload files to Hugging Face repository
def upload_files(folder_path, repo_id, token, private, threads, subfolder, repo_type):
    if cancel_event.is_set():
        log("❌ Upload has been cancelled.")
        return "❌ Upload has been cancelled."

    # Validate inputs early
    if not os.path.isdir(folder_path):
        log(f"❌ The folder path '{folder_path}' does not exist.")
        return f"❌ The folder path '{folder_path}' does not exist."
    
    if not validate_repo_id(repo_id)[0] or not token:
        return "❌ Repository ID and Hugging Face Token are required."

    # Check if there are files to upload only once
    if not os.listdir(folder_path):
        log(f"⚠️ No files to upload in '{folder_path}'. Skipping...")
        return

    # Prepare upload parameters
    target_path = subfolder.replace("\\", "/") if subfolder else ""
    
    # Authenticate and create repository if necessary
    success, auth_message = authenticate(token)
    if not success:
        return auth_message

    success, creation_message = create_repo_if_not_exists(repo_id, token, repo_type, private)
    if not success:
        return creation_message

    # Use upload_folder for the entire folder upload
    upload_params = {
        "folder_path": folder_path,
        "repo_id": repo_id,
        "repo_type": repo_type,
        "token": token,
        "path_in_repo": target_path,  # Directly specify the path in repo
        "ignore_patterns": ["**/.DS_Store"],
        "multi_commits": True,
        "multi_commits_verbose": True,
    }

    log(f"🚀 Uploading folder '{folder_path}' to '{target_path}' in repository '{repo_id}'...")
    try:
        upload_folder(**upload_params)
        log(f"✅ Upload completed for '{folder_path}'!")
    except Exception as upload_err:
        log(f"❌ Upload failed for '{folder_path}': {upload_err}")

    return "🚀 Upload completed. Check the logs for details."

# Function to get tree structure of a local folder
def get_local_tree(folder_path):
    if not os.path.isdir(folder_path):
        return "❌ Invalid folder path."

    tree = {}
    for root, dirs, files in os.walk(folder_path):
        level = root.replace(folder_path, '').count(os.sep)
        indent = " " * 4 * level
        tree_line = f"{indent}📁 {os.path.basename(root)}/"
        tree[tree_line] = {}
        sub_indent = " " * 4 * (level + 1)
        for f in files:
            tree[f"{sub_indent}📄 {f}"] = {}
    return "\n".join(tree.keys())

# Function to get tree structure of a remote repository
# Function to get tree structure of a remote repository
def get_remote_tree(repo_id, token, subfolder, repo_type):
    try:
        files = list_repo_files(repo_id=repo_id, token=token, repo_type=repo_type)  # Removed 'path' argument
        tree = {}
        for file in files:
            parts = file.split('/')
            current = tree
            for part in parts:
                current = current.setdefault(part, {})
        def build_tree(d, prefix=""):
            lines = []
            for key, subtree in d.items():
                if subtree:
                    lines.append(f"📁 {prefix}{key}/")
                    lines.extend(build_tree(subtree, prefix + "    "))
                else:
                    lines.append(f"📄 {prefix}{key}")
            return lines
        return "\n".join(build_tree(tree))
    except Exception as e:
        log(f"❌ Failed to fetch remote tree: {e}")
# Function to refresh remote tree
def refresh_remote(repo_id, token, subfolder, repo_type):
    return get_remote_tree(repo_id, token, subfolder, repo_type)

# Function to cancel upload
def cancel_upload():
    cancel_event.set()
    log("⚠️ Upload cancellation requested.")
    return "Upload cancellation requested."

# Function to refresh local tree
def refresh_local(folder_path):
    return get_local_tree(folder_path)

# Function to refresh logs
def refresh_logs():
    return "\n".join(shared_logs[-100:])  # Show last 100 logs

# Gradio Interface
def create_interface():
    with gr.Blocks() as app:
        gr.Markdown("# 🚀 InfiniteStorageFace")
        gr.Markdown("**Effortlessly upload your files to Hugging Face repositories with real-time feedback and progress tracking!**")

        with gr.Row():
            token = gr.Textbox(
                label="Hugging Face Token",
                type="password",
                placeholder="Enter your Hugging Face API token",
                value=SAMPLE_TOKEN,
                interactive=True,
                max_lines=1,
                scale=2,
            )

            repo_type = gr.Dropdown(
                label="Repository Type",
                choices=["space", "model", "dataset"],
                value="space",
                interactive=True,
                scale=1,
            )

        with gr.Row():
            repo_id = gr.Textbox(
                label="Repository ID",
                placeholder="e.g., username/repo-name",
                value=SAMPLE_REPO_ID,
                interactive=True,
                lines=1,
                scale=3,
            )

            private = gr.Checkbox(
                label="Make Repository Private",
                value=False,
                interactive=True,
                scale=1,
            )

        with gr.Row():
            folder_path = gr.Textbox(
                label="Folder Path to Upload",
                placeholder="Enter the absolute path to your folder",
                value=SAMPLE_FOLDER_PATH,
                interactive=True,
                lines=1,
                scale=3,
            )

            subfolder = gr.Textbox(
                label="Subfolder in Repository (Optional)",
                placeholder="e.g., data/uploads",
                value="",
                interactive=True,
                lines=1,
                scale=2,
            )

        with gr.Row():
            threads = gr.Slider(
                label="Number of Threads",
                minimum=1,
                maximum=20,
                step=1,
                value=SAMPLE_THREADS,
                interactive=True,
                scale=1,
            )

            process_individually = gr.Checkbox(
                label="Process First-Level Folders Individually",
                value=False,
                interactive=True,
                scale=1,
            )

        with gr.Row():
            upload_button = gr.Button("Start Upload", variant="primary", interactive=True)
            cancel_button = gr.Button("Cancel Upload", variant="secondary", interactive=True)

        with gr.Row():
            upload_status = gr.Textbox(label="Upload Status", lines=1, interactive=False, value="Idle", scale=3)

        with gr.Tab("Logs"):
            with gr.Row():
                log_output = gr.Textbox(label="Upload Logs", lines=15, interactive=False, placeholder="Logs will appear here...")
                log_refresh = gr.Button("Refresh Logs", interactive=True)

        with gr.Tab("Repository Trees"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### Local Folder Structure")
                    local_tree = gr.Textbox(value=get_local_tree(SAMPLE_FOLDER_PATH), lines=20, interactive=False, placeholder="Local folder tree will appear here...")
                    local_refresh = gr.Button("Refresh Local Tree", interactive=True)

                with gr.Column(scale=1):
                    gr.Markdown("### Remote Repository Structure")
                    remote_tree = gr.Textbox(value=get_remote_tree(SAMPLE_REPO_ID, SAMPLE_TOKEN, "", "space"), lines=20, interactive=False, placeholder="Remote repository tree will appear here...")
                    remote_refresh = gr.Button("Refresh Remote Tree", interactive=True)

        with gr.Tab("Documentation"):
            gr.Markdown(
                """
### **Storage Focused Documentation**

1. **Hugging Face Token**: Obtain your API token from your [Hugging Face account settings](https://huggingface.co/settings/tokens).

2. **Repository Type**: Select the type of repository you want to upload to:
    - **Space**: For deploying machine learning apps. Use the `static` SDK for simple deployments.
    - **Model**: For sharing machine learning models.
    - **Dataset**: For sharing datasets.

3. **Repository ID**: Format is `username/repo-name`. If it doesn't exist, it will be created with `static` SDK by default.

4. **Make Repository Private**: Check this to create a private repository.

5. **Folder Path to Upload**: Specify the absolute path to your local folder.

6. **Subfolder in Repository (Optional)**: Specify a subdirectory within the repository. Leave it empty to upload to the root directory.

7. **Number of Threads**: Adjust threads for optimizing upload speed. Start with 5 for a balance between speed and stability.

8. **Free Storage Tips**:
   - Use `Dataset` for sharing data with others; you can upload large datasets without incurring costs.
   - `Model` repositories are ideal for reusable models, making it easy to share with the community.
   - Ensure that your files comply with Hugging Face guidelines to avoid storage issues.

9. **Start Upload**: Click to begin uploading. Monitor progress in the `Upload Status` and `Logs` tabs.

10. **Logs**: View logs in real-time and refresh them as needed.

11. **Repository Trees**: View and refresh the structure of your local folder and remote repository.

**Note:** Ensure that your files do not contain sensitive information such as API keys or tokens. Files detected with sensitive information may cause upload failures.
"""
            )

        # Define the upload button click event
        upload_button.click(
            fn=upload_files, 
            inputs=[folder_path, repo_id, token, private, threads, subfolder, repo_type, process_individually], 
            outputs=upload_status
        )

        # Define the cancel button click event
        cancel_button.click(fn=cancel_upload, inputs=None, outputs=upload_status)

        # Define the log refresh button click event
        log_refresh.click(fn=refresh_logs, inputs=None, outputs=log_output)

        # Define the local tree refresh button click event
        local_refresh.click(fn=refresh_local, inputs=folder_path, outputs=local_tree)

        # Define the remote tree refresh button click event
        remote_refresh.click(fn=refresh_remote, inputs=[repo_id, token, subfolder, repo_type], outputs=remote_tree)

        # Background thread to update logs in real-time
        def update_logs():
            while True:
                while not log_queue.empty():
                    new_log = log_queue.get()
                    # Update log_output if it's still active
                    if log_output.value is not None:
                        current_logs = log_output.value
                        updated_logs = f"{current_logs}{new_log}\n"
                        log_output.value = updated_logs
                time.sleep(1)

        Thread(target=update_logs, daemon=True).start()

    return app

# Launch the Gradio app with public link
if __name__ == "__main__":
    app = create_interface()
    app.launch(debug=True, share=True)
