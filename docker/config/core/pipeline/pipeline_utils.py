import asyncio
from pathlib import Path
from typing import List, Union
import aiohttp
from loguru import logger
import os

from inference.core.env import MODEL_CACHE_DIR


VIDEO_DOWNLOAD_DIR = Path(os.path.join(MODEL_CACHE_DIR, "pipeline_videos"))
VIDEO_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def download_video(video_url: str) -> str:
    try:
        filename = video_url.split("/")[-1].split("?")[0]
        if "." not in filename:
            filename = f"{filename}.mp4"
        pipeline_dir = VIDEO_DOWNLOAD_DIR
        pipeline_dir.mkdir(parents=True, exist_ok=True)
        local_path = pipeline_dir / filename
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url) as response:
                if response.status == 200:
                    with open(local_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                    logger.info(f"Downloaded video from {video_url} to {local_path}")
                    return str(local_path)
                else:
                    logger.error(
                        f"Failed to download video from {video_url}, status: {response.status}"
                    )
                    return video_url
    except Exception as e:
        logger.error(f"Error downloading video from {video_url}: {str(e)}")
        return video_url


async def download_videos_parallel(video_references: List[Union[str, int]]) -> List[Union[str, int]]:
    tasks = []
    for ref in video_references:
        if isinstance(ref, str) and ref.startswith(("http://", "https://")):
            tasks.append(download_video(ref))
        else:
            tasks.append(asyncio.sleep(0, result=ref))
    results = await asyncio.gather(*tasks)
    return results


def cleanup_pipeline_videos(pipeline_id: str) -> None:
    try:
        pipeline_dir = VIDEO_DOWNLOAD_DIR / pipeline_id
        if pipeline_dir.exists():
            import shutil
            shutil.rmtree(pipeline_dir)
            logger.info(f"Cleaned up video files for pipeline {pipeline_id}")
    except Exception as e:
        logger.error(f"Error cleaning up video files for pipeline {pipeline_id}: {str(e)}")


