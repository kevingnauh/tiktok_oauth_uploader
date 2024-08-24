# orchestration

"""
Uses the scoped access token to post videos with user's authorization.

Direct Post API:
https://developers.tiktok.com/doc/content-posting-api-reference-direct-post/


# Media transfer guideline:
https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide
"""

import json
import os
import requests
import math
from utils import retry_on_failure, log_error, read_json, get_access_token_from_file
from config import USER_TOKEN_FILENAME

# Invoke post endpoint to get an upload URL 
def initialize_video_upload(access_token, video_size, title, **kwargs):
    """
    Function to initialize video upload with tiktok server.
    """
    privacy_level = kwargs.get('privacy_level', "SELF_ONLY")
    disable_duet = kwargs.get('disable_duet', False)
    disable_comment = kwargs.get('disable_comment', False)
    disable_stitch = kwargs.get('disable_stitch', False)
    video_cover_timestamp_ms = kwargs.get('video_cover_timestamp_ms', None)
    brand_content_toggle = kwargs.get('brand_content_toggle', False)
    brand_organic_toggle = kwargs.get('brand_organic_toggle', False)
    is_aigc = kwargs.get('is_aigc', False)

    url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8"
    }

    chunk_size = min(64_000_000, video_size)
    total_chunk_count = (video_size // chunk_size) + (1 if video_size % chunk_size > 0 else 0)-1

    # Post upload required fields
    post_info = {
        "title": title,
        "privacy_level": privacy_level,
        "disable_duet": disable_duet,
        "disable_comment": disable_comment,
        "disable_stitch": disable_stitch,
        "brand_content_toggle": brand_content_toggle,
        "brand_organic_toggle": brand_organic_toggle,
        "is_aigc": is_aigc
    }

    # Add video cover timestamp
    if video_cover_timestamp_ms is not None:
        post_info["video_cover_timestamp_ms"] = video_cover_timestamp_ms

    # File upload required fields
    source_info = {
        "source": "FILE_UPLOAD",
        "video_size": video_size,
        "chunk_size": chunk_size,
        "total_chunk_count": total_chunk_count
    }

    data = {
        "post_info": post_info,
        "source_info": source_info
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()['data'] , source_info
    else:
        log_error(f"Error initializing video upload: {response.status_code} - {response.text}")
        return None

# Splits video file into chunks and prepare it for upload.
# per the media transfer guidelines, the last chunk needs to be merged if it is atleast 5MB and less than 64MB
def upload_video_to_tiktok(upload_url, video_path, chunk_size):
    if os.path.exists(video_path) and os.path.isfile(video_path):
        video_size = os.path.getsize(video_path)

        # Calculate total chunks, leaving the last chunk to include the leftover bytes
        total_chunk_count = (video_size // chunk_size) + (1 if video_size % chunk_size > 0 else 0) - 1

        with open(video_path, 'rb') as video_file:
            for chunk_index in range(total_chunk_count):

                start_byte = chunk_index * chunk_size
                end_byte = min(start_byte + chunk_size, video_size) - 1

                remaining_bytes = video_size - end_byte 

                if remaining_bytes < chunk_size:
                    end_byte = video_size - 1

                print(f"chunk_index: {chunk_index} , start_byte: {start_byte}, end_byte: {end_byte}")
                
                video_file.seek(start_byte)
                chunk_data = video_file.read(end_byte - start_byte + 1)

                headers = {
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(chunk_data)),
                    "Content-Range": f"bytes {start_byte}-{end_byte}/{video_size}"
                }

                response = requests.put(upload_url, headers=headers, data=chunk_data)

                print(f"response.status_code: {response.status_code} - {response.text}")
    else:
        log_error(f"Invalid file: {video_path}")

# Get creator profile setting info - posting api requires upload metadata to match users profile setting
def query_creator_info(access_token):
    url = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8"
    }
    response = requests.post(url, headers=headers)
    if response.status_code == 200:
        return response.json()['data']
    else:
        log_error(f"Error querying creator info: {response.status_code} - {response.text}")
        return None

@retry_on_failure
def upload_video(video_path, description, user_id, access_token):
    # Get user's profile setting
    creator_info = query_creator_info(access_token)

    # if user info is not retrieved from info api for any reason, posting will fail. check if token expired first
    if creator_info is None: 
        log_error(f"Could not retrieve info for user {user_id}")
        return

    creator_info['privacy_level_options'] = creator_info.get('privacy_level_options', 'SELF_ONLY')[-1] # get last option or use highest privacy level
    override_params = {k: v for k, v in creator_info.items() if v is not None} # use defaults if key is missing 
    
    video_size = os.path.getsize(video_path)
    
    # Init upload request and get upload URL 
    init_data, s_info = initialize_video_upload(
        access_token=access_token,
        video_size=video_size,
        title=description,
        **override_params
    )

    # Split video file into appropriate chunks and upload
    if init_data:
        upload_url = init_data['upload_url']
        chunk_size = s_info['chunk_size']  
        upload_video_to_tiktok(upload_url, video_path, chunk_size)

def upload_all(videos):
    for entry in videos:
        try:
            video_path = entry['video_path']
            user_id = entry['user_id']
            description = entry['description']
            tags = entry['tags']
            description = description + " ".join(tags)
            
            # Get access_token from local json file
            # TODO: replace with database 
            access_token = get_access_token_from_file(user_id, USER_TOKEN_FILENAME)

            upload_video(video_path, description, user_id, access_token)
        except Exception as e:
            log_error(f"upload_all failed on entry: {entry} ErrorMsg: {e}")


if __name__ == '__main__':
    videos_to_upload = 'videos_to_upload.json'
    videos = read_json(videos_to_upload)
    upload_all(videos)
