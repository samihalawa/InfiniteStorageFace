# InfiniteStorageFace.py

import os
import gradio as gr
from huggingface_hub import HfApi, upload_folder, create_repo, list_repo_files
from threading import Thread
import queue
from plyer import notification  # For desktop notifications
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, TransferSpeedColumn

# Initialize Rich console for logging
console = Console()

# Initialize Hugging Face API client
api = HfApi()

# Queue for logging
log_queue = queue.Queue()

# Function to log messages and send desktop notifications
def log(message):
    log_queue.put(message)
    console.log(message)
    if "✅" in message:
        notification.notify(
            title='InfiniteStorageFace',
            message=message,
            timeout=5
        )
    elif "❌" in message:
        notification.notify(
            title='InfiniteStorageFace - Error',
            message=message,
            timeout=5
        )
    elif "🚀" in message:
        notification.notify(
            title='InfiniteStorageFace',
            message=message,
            timeout=3
        )

# Authenticate user to Hugging Face
def authenticate(token):
    try:
        api.login(token)
        log("✅ Authenticated successfully!")
        return "✅ Authenticated successfully!"
    except Exception as e:
        log(f"❌ Authentication failed: {e}")
        return f"❌ Authentication failed: {e}"

# Function to create a new Hugging Face repository
def create_repo_if_not_exists(repo_id, token, repo_type="dataset", private=False):
    try:
        # Check if repo exists by listing files
        api.list_repo_files(repo_id=repo_id, repo_type=repo_type, token=token)
        log(f"✅ Repo '{repo_id}' exists. Proceeding with upload...")
        return f"✅ Repo '{repo_id}' exists. Proceeding with upload..."
    except Exception:
        # Create repo if it does not exist
        try:
            create_repo(repo_id=repo_id, token=token, private=private, repo_type=repo_type)
            log(f"✅ Created new repo: '{repo_id}'.")
            return f"✅ Created new repo: '{repo_id}'."
        except Exception as create_err:
            log(f"❌ Failed to create repo: {create_err}")
            return f"❌ Failed to create repo: {create_err}"

# Function to upload files to Hugging Face repo
def upload_files(folder_path, repo_id, token, private=False, threads=5):
    def upload_process():
        # Step 1: Ensure repo exists
        creation_log = create_repo_if_not_exists(repo_id, token, private=private)
        log_text = f"{creation_log}\n🚀 Starting upload...\n"

        # Step 2: Upload files from the folder
        try:
            if not os.path.isdir(folder_path):
                log(f"❌ Folder path '{folder_path}' does not exist.")
                return

            files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
            total_files = len(files)
            log(f"📂 Found {total_files} files in folder '{folder_path}'. Uploading...")

            if total_files == 0:
                log("❌ No files found to upload.")
                return

            # Using Rich Progress for better visualization
            with Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                upload_task = progress.add_task("Uploading...", total=total_files)
                for _ in range(total_files):
                    progress.advance(upload_task)

                # Actual upload
                upload_folder(repo_id=repo_id, folder_path=folder_path, repo_type="dataset", token=token, num_threads=threads)

            log("✅ Upload complete!")
        except Exception as e:
            log(f"❌ Upload failed: {e}")

    # Start upload in a separate thread
    upload_thread = Thread(target=upload_process)
    upload_thread.start()

    return "🚀 Upload started. Check logs for progress."

# Function to continuously update logs
def update_logs():
    messages = []
    while not log_queue.empty():
        messages.append(log_queue.get())
    return "\n".join(messages)

# Gradio UI components
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
                    interactive=True
                )
                private = gr.Checkbox(
                    label="Make Repo Private",
                    value=False
                )

            folder_path = gr.Textbox(
                label="Folder Path to Upload",
                placeholder="Enter the path to your folder",
                interactive=True
            )
            repo_id = gr.Textbox(
                label="Repository ID",
                placeholder="e.g., your-username/your-repo",
                interactive=True
            )

            threads = gr.Slider(
                label="Number of Threads",
                minimum=1,
                maximum=20,
                step=1,
                value=5
            )

            upload_button = gr.Button(
                "Start Upload",
                variant="primary",
                interactive=True
            )
            upload_button.click(
                upload_files, 
                inputs=[folder_path, repo_id, token, private, threads], 
                outputs="log_output"
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
                interactive=True
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
        """)

    return app

# Launch the Gradio app
if __name__ == "__main__":
    app = create_interface()
    app.launch()
