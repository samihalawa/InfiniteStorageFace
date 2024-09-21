# InfiniteStorageFace.py

# Requirements:
# pip install gradio huggingface_hub rich python-dotenv

import os
import gradio as gr
from huggingface_hub import HfApi, upload_folder, create_repo, login, list_repo_files
from rich.console import Console
from rich.logging import RichHandler
import logging
import time
import dotenv
import shutil
from pathlib import Path

# Load environment variables
dotenv.load_dotenv()

# Default values
DEFAULT_REPO = os.getenv("DEFAULT_REPO", "luigi12345/megacursos1")
DEFAULT_LOCAL_PATH = os.getenv("DEFAULT_LOCAL_PATH", "/Users/samihalawa/git/BACKUP_IMAGES-main")

# Initialize Rich console for logging
console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%Y-%m-%d %H:%M:%S]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)]
)
logger = logging.getLogger("InfiniteStorageFace")

# Initialize Hugging Face API client
api = HfApi()

# Centralized ignore patterns mapping
IGNORE_PATTERNS_MAP = {
    "Ignore __pycache__": "**/__pycache__/**",
    "Ignore .git": ".git/**",
    "Ignore .venv": "venv/**",
    "Ignore *.pyc": "*.pyc",
    "Ignore *.log": "*.log",
    "Ignore *.tmp": "*.tmp",
    "Ignore *.DS_Store": "*.DS_Store"
}

# Shared logs list
shared_logs = []

# Event to cancel upload
cancel_event = False

# Function to log messages
def log(message):
    timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]")
    full_message = f"{timestamp} {message}"
    shared_logs.append(full_message)
    logger.info(message)
    return full_message

# Function to authenticate user with Hugging Face token
def authenticate(token):
    if not token:
        return False, log("❌ Hugging Face Token is required.")
    try:
        login(token)
        return True, log("✅ Authenticated successfully!")
    except Exception as e:
        return False, log(f"❌ Authentication failed: {e}")

# Function to create repository if it doesn't exist
def create_repo_if_not_exists(repo_id, token, repo_type, private):
    try:
        api.list_repo_files(repo_id=repo_id, repo_type=repo_type, token=token)
        return True, log(f"✅ Repository '{repo_id}' exists. Proceeding with upload...")
    except Exception:
        log(f"❌ Repository '{repo_id}' does not exist. Creating it...")
        try:
            create_repo(
                repo_id=repo_id,
                token=token,
                private=private,
                repo_type=repo_type,
                exist_ok=True,
                space_sdk="static" if repo_type == "space" else None
            )
            return True, log(f"✅ Created new repository: '{repo_id}'.")
        except Exception as create_err:
            return False, log(f"❌ Failed to create repository '{repo_id}': {create_err}")

# Function to delete specific folders before upload
def cleanup_before_upload(folder_path, ignore_patterns):
    for pattern in ignore_patterns:
        # Extract folder name from pattern (assuming patterns like '**/folder_name/**')
        folder_name = pattern.strip("/**")
        target_path = os.path.join(folder_path, folder_name)
        if os.path.exists(target_path):
            try:
                shutil.rmtree(target_path)
                log(f"🗑️ Deleted '{target_path}'.")
            except Exception as e:
                log(f"❌ Failed to delete '{target_path}': {e}")

# Function to upload a folder
def upload_folder_structure(folder_path, repo_id, token, repo_type, target_path, ignore_patterns):
    # Clean up ignored folders
    cleanup_before_upload(folder_path, ignore_patterns)

    upload_params = {
        "folder_path": folder_path,
        "repo_id": repo_id,
        "repo_type": repo_type,
        "token": token,
        "path_in_repo": target_path,
        "multi_commits": True,
        "multi_commits_verbose": True,
    }
    log(f"🚀 Uploading folder '{folder_path}' to '{target_path}' in repository '{repo_id}'...")
    try:
        upload_folder(**upload_params)
        log(f"✅ Upload completed for '{folder_path}'!")
    except Exception as upload_err:
        log(f"❌ Upload failed for '{folder_path}': {upload_err}")

# Function to handle uploads
def upload_files(folder_path, repo_id, token, private, threads, subfolder, repo_type, process_individually, ignore_patterns_selected):
    global cancel_event
    cancel_event = False
    
    logs = []
    
    # Authenticate
    auth_success, auth_message = authenticate(token)
    logs.append(auth_message)
    if not auth_success:
        return "\n".join(logs)
    
    # Create repo if not exists
    repo_success, repo_message = create_repo_if_not_exists(repo_id, token, repo_type, private)
    logs.append(repo_message)
    if not repo_success:
        return "\n".join(logs)
    
    # Prepare target path
    target_path = subfolder.replace("\\", "/") if subfolder else ""
    
    # Map selected ignore patterns to actual patterns
    ignore_patterns = [IGNORE_PATTERNS_MAP[pattern] for pattern in ignore_patterns_selected]
    
    # Check if folder exists
    if not os.path.isdir(folder_path):
        logs.append(log(f"❌ The folder path '{folder_path}' does not exist."))
        return "\n".join(logs)
    
    if process_individually:
        for item in os.listdir(folder_path):
            if cancel_event:
                logs.append(log("❌ Upload has been cancelled."))
                return "\n".join(logs)
            item_path = os.path.join(folder_path, item)
            if os.path.isdir(item_path):
                upload_folder_structure(item_path, repo_id, token, repo_type, f"{target_path}/{item}", ignore_patterns)
                logs.append(log(f"✅ Uploaded folder '{item_path}'."))
    else:
        upload_folder_structure(folder_path, repo_id, token, repo_type, target_path, ignore_patterns)
        logs.append(log("✅ Uploaded the entire folder."))
    
    if cancel_event:
        logs.append(log("❌ Upload has been cancelled."))
        return "\n".join(logs)
    
    logs.append(log("🚀 Upload completed. Check the logs for details."))
    return "\n".join(logs)

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
def get_remote_tree(repo_id, token, subfolder, repo_type):
    try:
        files = list_repo_files(repo_id=repo_id, token=token, repo_type=repo_type)
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
        return f"❌ Failed to fetch remote tree: {e}"

# Function to cancel upload
def cancel_upload():
    global cancel_event
    cancel_event = True
    log("❌ Upload has been cancelled.")
    return "❌ Upload has been cancelled."

# Function to refresh logs
def refresh_logs():
    return "\n".join(shared_logs)

# Function to refresh local tree
def refresh_local(folder_path):
    return get_local_tree(folder_path)

# Function to refresh remote tree
def refresh_remote(repo_id, token, subfolder, repo_type):
    return get_remote_tree(repo_id, token, subfolder, repo_type)

# Gradio Interface
def create_interface():
    with gr.Blocks() as app:
        gr.Markdown("# 🚀 InfiniteStorageFace")
        gr.Markdown("**Effortlessly upload your files to Hugging Face repositories with real-time feedback and progress tracking!**")
        
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("## Upload Section")
                
                token = gr.Textbox(
                    label="Hugging Face Token",
                    type="password",
                    placeholder="Enter your Hugging Face API token",
                    value="",  # Remove prefilled sample token for security
                    interactive=True,
                    lines=1,
                )
                
                repo_type = gr.Dropdown(
                    label="Repository Type",
                    choices=["space", "model", "dataset"],
                    value="space",
                    interactive=True,
                )
                
                repo_id = gr.Textbox(
                    label="Repository ID",
                    placeholder="e.g., username/repo-name",
                    value=DEFAULT_REPO,
                    interactive=True,
                    lines=1,
                )
                
                private = gr.Checkbox(
                    label="Make Repository Private",
                    value=False,
                    interactive=True,
                )
                
                folder_path = gr.Textbox(
                    label="Folder Path to Upload",
                    placeholder="Enter the absolute path to your folder",
                    value=DEFAULT_LOCAL_PATH,
                    interactive=True,
                    lines=1,
                )
                
                subfolder = gr.Textbox(
                    label="Subfolder in Repository (Optional)",
                    placeholder="e.g., data/uploads",
                    value="",
                    interactive=True,
                    lines=1,
                )
                
                threads = gr.Slider(
                    label="Number of Threads",
                    minimum=1,
                    maximum=20,
                    step=1,
                    value=5,
                    interactive=True,
                )
                
                process_individually = gr.Checkbox(
                    label="Process First-Level Folders Individually",
                    value=False,
                    interactive=True,
                )
                
                ignore_patterns_selected = gr.CheckboxGroup(
                    choices=list(IGNORE_PATTERNS_MAP.keys()),
                    label="Select Patterns to Ignore",
                    value=["Ignore __pycache__", "Ignore .git", "Ignore *.pyc"],
                    interactive=True,
                )
                
                upload_button = gr.Button("Start Upload", variant="primary", interactive=True)
                cancel_button = gr.Button("Cancel Upload", variant="secondary", interactive=True)
            
            with gr.Column(scale=1):
                gr.Markdown("## Status Section")
                upload_status = gr.Textbox(
                    label="Upload Status",
                    lines=10,
                    interactive=False,
                    value="Idle",
                )
                
                with gr.Tab("Logs"):
                    log_output = gr.Textbox(
                        label="Upload Logs",
                        lines=15,
                        interactive=False,
                        placeholder="Logs will appear here...",
                        value="",
                    )
                    log_refresh = gr.Button("Refresh Logs", interactive=True)
                
                with gr.Tab("Repository Trees"):
                    local_tree = gr.Textbox(
                        label="Local Folder Tree",
                        value=get_local_tree(DEFAULT_LOCAL_PATH),
                        lines=20,
                        interactive=False,
                        placeholder="Local folder tree will appear here...",
                    )
                    local_refresh = gr.Button("Refresh Local Tree", interactive=True)
                    
                    remote_tree = gr.Textbox(
                        label="Remote Repository Tree",
                        value=get_remote_tree(DEFAULT_REPO, "", "", "space"),
                        lines=20,
                        interactive=False,
                        placeholder="Remote repository tree will appear here...",
                    )
                    remote_refresh = gr.Button("Refresh Remote Tree", interactive=True)
                
                with gr.Tab("Documentation"):
                    gr.Markdown(
                        """### **Storage Focused Documentation**
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
            inputs=[
                folder_path,
                repo_id,
                token,
                private,
                threads,
                subfolder,
                repo_type,
                process_individually,
                ignore_patterns_selected
            ],
            outputs=upload_status
        )
        
        # Define the cancel button click event
        cancel_button.click(
            fn=cancel_upload,
            inputs=None,
            outputs=upload_status
        )
        
        # Define the log refresh button click event
        log_refresh.click(
            fn=refresh_logs,
            inputs=None,
            outputs=log_output
        )
        
        # Define the local tree refresh button click event
        local_refresh.click(
            fn=refresh_local,
            inputs=folder_path,
            outputs=local_tree
        )
        
        # Define the remote tree refresh button click event
        remote_refresh.click(
            fn=refresh_remote,
            inputs=[repo_id, token, subfolder, repo_type],
            outputs=remote_tree
        )
        
        return app

    # Launch the Gradio app with public link
if __name__ == "__main__":
        app = create_interface()
        app.launch(debug=True, share=True)
