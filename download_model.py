from huggingface_hub import snapshot_download


snapshot_download(
    repo_id="BAAI/bge-small-zh",
    local_dir="./models/bge-small-zh"
)