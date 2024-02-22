from pathlib import Path

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient


def download_blob(
    blob_path: str | Path, blob_conn_str: str, local_path: Path = Path(".")
):
    local_path.mkdir(exist_ok=True, parents=True)
    container, blob_path = str(blob_path).split("/", maxsplit=1)
    blob_path = Path(blob_path)
    blob_service_client: BlobServiceClient = BlobServiceClient.from_connection_string(
        blob_conn_str
    )
    container_client = blob_service_client.get_container_client(container)
    out_path = local_path / blob_path.name
    try:
        with open(out_path, "wb") as my_blob:
            blob_data = container_client.download_blob(str(blob_path))
            blob_data.readinto(my_blob)
        return out_path
    except ResourceNotFoundError as e:
        out_path.unlink()
        raise ValueError(f"Invalid blob path: {container}/{str(blob_path)}") from e
