# InfiniteStorageFace.py
# Required Libraries:
# pip install streamlit huggingface_hub

import os
import streamlit as st
from huggingface_hub import HfApi, create_repo, upload_file, login
from threading import Thread, Event, Lock
import time
import re

# ----------------------------
# Set Page Configuration
# ----------------------------
st.set_page_config(page_title="🚀 InfiniteStorageFace", layout="wide")

# ----------------------------
# Configuration and Constants
# ----------------------------

# Regular expression for validating repository ID
REPO_ID_REGEX = re.compile(r"^[a-zA-Z0-9\-_.]+/[a-zA-Z0-9\-_.]+$")

# Prefilled sample values (placeholders)
SAMPLE_TOKEN = ""  # Leave empty for security; user must input
SAMPLE_FOLDER_PATH = "/Users/samihalawa/Documents/Megacursos/MEGACURSOS_S3_MASTER/angular"
SAMPLE_REPO_ID = "luigi12345/megacursos1"
SAMPLE_THREADS = 5

# ----------------------------
# Global Variables and Locks
# ----------------------------

# Event to signal upload cancellation
cancel_event = Event()

# Lock for thread-safe operations
upload_lock = Lock()

# Shared log list (in-memory cache)
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'uploading' not in st.session_state:
    st.session_state.uploading = False

# ----------------------------
# Helper Functions
# ----------------------------

def log(message):
    """Logs a message by adding it to the shared_logs list."""
    with upload_lock:
        st.session_state.logs.append(message)

def authenticate(token):
    """Authenticates the user with Hugging Face using the provided token."""
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

def validate_repo_id(repo_id):
    """Validates the format of the repository ID."""
    if not repo_id:
        log("❌ Repository ID is required.")
        return False, "❌ Repository ID is required."
    if not REPO_ID_REGEX.match(repo_id):
        log("❌ Repository ID must be in the format 'username/repo-name'.")
        return False, "❌ Repository ID must be in the format 'username/repo-name'."
    return True, "✅ Repository ID format is valid."

def create_repo_if_not_exists(repo_id, token, repo_type="space", private=False):
    """Creates a repository if it does not exist."""
    api = HfApi()
    try:
        # Check if the repository exists by listing its files
        api.list_repo_files(repo_id=repo_id, repo_type=repo_type, token=token)
        log(f"✅ Repository '{repo_id}' exists. Proceeding with upload...")
        return True, f"✅ Repository '{repo_id}' exists. Proceeding with upload..."
    except Exception:
        # If repository does not exist, create it
        try:
            create_repo(repo_id=repo_id, token=token, private=private, repo_type=repo_type, exist_ok=True)
            log(f"✅ Created new repository: '{repo_id}'.")
            return True, f"✅ Created new repository: '{repo_id}'."
        except Exception as create_err:
            log(f"❌ Failed to create repository '{repo_id}': {create_err}")
            return False, f"❌ Failed to create repository '{repo_id}': {create_err}"

def upload_files(folder_path, repo_id, token, private=False, threads=5, subfolder=None):
    """Handles the uploading of files to the Hugging Face repository."""
    if cancel_event.is_set():
        log("❌ Upload has been cancelled.")
        return "❌ Upload has been cancelled."

    # Validate inputs
    if not folder_path:
        log("❌ Folder Path is required.")
        return "❌ Folder Path is required."
    
    # Normalize the folder path
    folder_path = os.path.normpath(folder_path).strip()
    
    if not os.path.isabs(folder_path):
        log("❌ Please provide an absolute folder path.")
        return "❌ Please provide an absolute folder path."
    
    if not os.path.isdir(folder_path):
        log(f"❌ The folder path '{folder_path}' does not exist.")
        return f"❌ The folder path '{folder_path}' does not exist."
    
    if not repo_id:
        log("❌ Repository ID is required.")
        return "❌ Repository ID is required."
    
    valid, message = validate_repo_id(repo_id)
    if not valid:
        return message
    
    if not token:
        log("❌ Hugging Face Token is required.")
        return "❌ Hugging Face Token is required."

    # Check if the folder contains files
    if not any(os.scandir(folder_path)):
        log("❌ The folder is empty. No files to upload.")
        return "❌ The folder is empty. No files to upload."

    def upload_process():
        with upload_lock:
            st.session_state.uploading = True
            try:
                # Step 1: Authenticate
                success, auth_message = authenticate(token)
                if not success:
                    st.session_state.uploading = False
                    return

                # Step 2: Create repository if it doesn't exist
                success, creation_message = create_repo_if_not_exists(repo_id, token, repo_type="space", private=private)
                if not success:
                    st.session_state.uploading = False
                    return

                # Step 3: Start upload
                log("🚀 Starting upload process...")
                start_time = time.time()

                # Iterate through all files in the folder
                total_files = sum(len(files) for _, _, files in os.walk(folder_path))
                uploaded_files = 0

                for root, dirs, files in os.walk(folder_path):
                    for file in files:
                        if cancel_event.is_set():
                            log("⚠️ Upload cancelled by user.")
                            st.session_state.uploading = False
                            return
                        file_path = os.path.join(root, file)
                        relative_path = os.path.relpath(file_path, folder_path)
                        repo_path = os.path.join(subfolder, relative_path) if subfolder else relative_path
                        try:
                            upload_file(
                                path_or_fileobj=file_path,
                                path_in_repo=repo_path,
                                repo_id=repo_id,
                                token=token,
                                repo_type="space",
                                commit_message=f"Add {relative_path}"
                            )
                            uploaded_files += 1
                            log(f"✅ Uploaded: {relative_path} ({uploaded_files}/{total_files})")
                        except Exception as e:
                            log(f"❌ Failed to upload {relative_path}: {e}")

                elapsed_time = time.time() - start_time
                log(f"✅ Upload completed successfully in {int(elapsed_time)} seconds!")
            except Exception as e:
                log(f"❌ An unexpected error occurred during upload: {e}")
            finally:
                st.session_state.uploading = False

    # Start the upload process in a separate thread to keep the UI responsive
    upload_thread = Thread(target=upload_process, daemon=True)
    upload_thread.start()

    return "🚀 Upload initiated. Check the logs for progress."

def display_logs(log_container):
    """Displays the logs from st.session_state.logs."""
    with log_container.container():
        if st.session_state.logs:
            # Join all log messages with newlines
            log_text = "\n".join(st.session_state.logs)
            # Display in a read-only text area with auto-scroll
            st.text_area("📜 Upload Logs", log_text, height=400, key='log_text', disabled=True)
        else:
            st.text_area("📜 Upload Logs", "Logs will appear here...", height=400, key='log_text', disabled=True)

def render_tree(tree, indent=0, max_depth=3, current_depth=0):
    """Recursively render the folder structure, limiting depth to simplify display."""
    if current_depth >= max_depth:
        return
    for key, value in sorted(tree.items()):
        if value is None:
            st.markdown(" " * indent + f"- {key}")
        else:
            st.markdown(" " * indent + f"- **{key}/**")
            render_tree(value, indent + 2, max_depth, current_depth + 1)

# ----------------------------
# Main Application
# ----------------------------

def main():
    # Auto-refresh every 1 second to update logs
    # Note: This approach can be heavy on resources. Use with caution.
    st_autorefresh = getattr(st, "autorefresh", None)
    if st_autorefresh:
        st.autorefresh(interval=1000, limit=1000, key="log_refresh")

    st.title("🚀 InfiniteStorageFace")
    st.markdown("**Effortlessly upload your files to Hugging Face Spaces with real-time feedback and progress tracking!**")

    # Sidebar for configuration
    with st.sidebar:
        st.header("📋 Configuration")

        token = st.text_input(
            "Hugging Face Token",
            type="password",
            placeholder="Enter your Hugging Face API token",
            value=SAMPLE_TOKEN,
        )

        private = st.checkbox(
            "Make Repository Private",
            value=False,
        )

        folder_path = st.text_input(
            "Folder Path to Upload",
            placeholder="Enter the absolute path to your folder",
            value=SAMPLE_FOLDER_PATH,
        )

        repo_id = st.text_input(
            "Repository ID",
            placeholder="e.g., username/repo-name",
            value=SAMPLE_REPO_ID,
        )

        subfolder = st.text_input(
            "Subfolder in Repository (optional)",
            placeholder="e.g., data/uploads",
            value="",
        )

        threads = st.slider(
            "Number of Threads",
            min_value=1,
            max_value=20,
            value=SAMPLE_THREADS,
            help="Adjust the number of threads to optimize upload speed based on your internet connection.",
        )

        upload_button = st.button("Start Upload")
        cancel_button = st.button("Cancel Upload")

    # Main area for logs and folder structure
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("📜 Upload Logs")
        log_container = st.empty()
        display_logs(log_container)
        if st.button("Clear Logs"):
            with upload_lock:
                st.session_state.logs = []
            log_container.empty()

    with col2:
        st.subheader("📁 Folder Structure")
        if os.path.isabs(folder_path) and os.path.isdir(folder_path):
            tree = {}
            for root, dirs, files in os.walk(folder_path):
                sub_dir = root.replace(folder_path, "").strip(os.sep)
                parent = tree
                if sub_dir:
                    for part in sub_dir.split(os.sep):
                        parent = parent.setdefault(part, {})
                for d in dirs:
                    parent[d] = {}
                for f in files:
                    parent[f] = None

            render_tree(tree)
        else:
            st.warning("Please enter a valid absolute folder path to display its structure.")

    # Handle upload and cancellation
    if upload_button and not st.session_state.uploading:
        # Clear previous logs
        with upload_lock:
            st.session_state.logs = []
        cancel_event.clear()
        status = upload_files(folder_path, repo_id, token, private, threads, subfolder)
        log(status)
    elif upload_button and st.session_state.uploading:
        st.warning("🚀 Upload is already in progress.")

    if cancel_button and st.session_state.uploading:
        cancel_event.set()
        log("⚠️ Upload cancellation requested.")

    st.markdown("""
    ---
    **📌 Instructions**:
    1. **Hugging Face Token**: Obtain your API token from your [Hugging Face account settings](https://huggingface.co/settings/tokens).
    2. **Folder Path**: Specify the absolute path to the folder you want to upload.
    3. **Repository ID**: Enter the desired repository name in the format `username/repo-name`.
    4. **Subfolder in Repository**: Optionally, specify a subfolder in the repository to upload your files into.
    5. **Number of Threads**: Adjust the number of threads to optimize upload speed based on your internet connection.
    6. **Start Upload**: Click to begin uploading your files.
    7. **Cancel Upload**: Click to cancel an ongoing upload process.
    8. **Clear Logs**: Click to clear the upload logs.
    """)

if __name__ == "__main__":
    main()
