import os.path
import shutil
import zipfile
from typing import Generator

import cv2
import numpy as np
import pytest
import requests

from inference.core.env import MODEL_CACHE_DIR

ASSETS_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "assets",
    )
)
EXAMPLE_IMAGE_PATH = os.path.join(ASSETS_DIR, "example_image.jpg")
PERSON_IMAGE_PATH = os.path.join(ASSETS_DIR, "person_image.jpg")
BEER_IMAGE_PATH = os.path.join(ASSETS_DIR, "beer.jpg")
TRUCK_IMAGE_PATH = os.path.join(ASSETS_DIR, "truck.jpg")
SAM2_TRUCK_LOGITS = os.path.join(ASSETS_DIR, "low_res_logits.npy")


@pytest.fixture(scope="function")
def example_image() -> np.ndarray:
    return cv2.imread(EXAMPLE_IMAGE_PATH)


@pytest.fixture(scope="function")
def yolov8_det_model() -> Generator[str, None, None]:
    model_id = "yolov8_det/1"
    model_cache_dir = fetch_and_place_model_in_cache(
        model_id=model_id,
        model_package_url="https://storage.googleapis.com/roboflow-tests-assets/yolov8_det.zip",
    )
    yield model_id
    shutil.rmtree(model_cache_dir)


def fetch_and_place_model_in_cache(
    model_id: str,
    model_package_url: str,
) -> str:
    target_model_directory = os.path.join(MODEL_CACHE_DIR, model_id)
    if os.path.isdir(target_model_directory):
        shutil.rmtree(target_model_directory)
    download_location = os.path.join(ASSETS_DIR, os.path.basename(model_package_url))
    if not os.path.exists(download_location):
        download_file(file_url=model_package_url, target_path=download_location)
    extract_zip_package(zip_path=download_location, target_dir=target_model_directory)
    return target_model_directory


def download_file(
    file_url: str,
    target_path: str,
    chunk_size: int = 8192,
) -> None:
    with requests.get(file_url, stream=True) as response:
        response.raise_for_status()
        with open(target_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=chunk_size):
                file.write(chunk)


def extract_zip_package(zip_path: str, target_dir: str) -> None:
    os.makedirs(target_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(target_dir)
