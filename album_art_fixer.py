#!/usr/bin/python

import logging
from typing import List
import urllib.parse
import urllib.request
import requests
import os
import tempfile
import asyncio
import aiohttp
import aiofiles
import json

g_logger = logging.getLogger(__name__)


from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC


async def set_album_art_in_audio_file(mp3_file_path: str, image_file_path: str) -> None:
    audio = MP3(mp3_file_path, ID3=ID3)
    async with aiofiles.open(image_file_path, "rb") as img_file:
        img_data = await img_file.read()

    try:
        audio.add_tags()  # Add ID3 tag if it doesn't exist
    except:
        pass

    assert audio.tags is not None
    audio.tags.add(
        APIC(
            encoding=3,  # 3 is for utf-8
            mime="image/jpeg",
            type=3,  # 3 is for the cover image
            desc="Cover",
            data=img_data,
        )
    )
    await asyncio.to_thread(audio.save)


async def download_album_art_from_itunes(song_title: str, dest_path: str) -> None:
    query = urllib.parse.quote(song_title)
    url = f"https://itunes.apple.com/search?term={query}&entity=song&limit=25"
    g_logger.info(f"\turl: {url}")

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            text = await response.text()
            data = json.loads(text.replace("\n", ""))

    for res_i in range(0, data["resultCount"]):
        result = data["results"][res_i]
        if "artworkUrl100" in result:
            image_url = result["artworkUrl100"].replace("100x100", "256x256")
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        async with aiofiles.open(dest_path, "wb") as f:
                            await f.write(await response.read())
                            return
    raise RuntimeError("No suitable album art found")


async def process_single_file(mp3_path: str) -> None:
    try:
        await find_and_set_new_album_art(mp3_path)
    except Exception as e:
        g_logger.error(f"Failed to process [{mp3_path}] due to : {e}", exc_info=True)
        raise


async def find_and_set_new_album_art(song_path: str) -> None:
    song_title = song_path.split(os.path.sep)[-1].split(".")[0]
    with tempfile.TemporaryDirectory() as temp_dir:
        album_art_path = os.path.join(temp_dir, f"{song_title.replace(' ', '_')}.jpg")
        await download_album_art_from_itunes(song_title, album_art_path)
        await set_album_art_in_audio_file(song_path, album_art_path)


async def process_mp3_files(dir_path: str) -> List[str]:
    failures = []
    for root, dirs, files in os.walk(dir_path):
        tasks = []
        for file in files:
            if file.lower().endswith(".mp3"):
                mp3_path = os.path.join(root, file)
                task = asyncio.create_task(process_single_file(mp3_path))
                tasks.append(task)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        failures.extend(
            [os.path.join(root, mp3_path) for mp3_path, result in zip(files, results)]
        )
        for dir in dirs:
            failures += await process_mp3_files(os.path.join(root, dir))
    return failures


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    g_logger.info("begin")
    failures = await process_mp3_files(
        "/Volumes/workspace/personal/album_art_fixer/songs"
    )
    g_logger.info(failures)


if __name__ == "__main__":
    asyncio.run(main())
