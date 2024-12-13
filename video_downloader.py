import os
from pytube import YouTube

def download_youtube_video(video_url, download_path="Downloads"):
    try:
        # Create download directory if it doesn't exist
        os.makedirs(download_path, exist_ok=True)
        
        # Initialize YouTube object
        yt = YouTube(video_url)
        
        # Print video details
        print(f"Title: {yt.title}")
        print(f"Author: {yt.author}")
        print(f"Length: {yt.length // 60} minutes {yt.length % 60} seconds")
        
        # Get highest resolution stream
        video_stream = yt.streams.get_highest_resolution()
        
        # Download the video
        print(f"Downloading '{yt.title}'...")
        video_stream.download(output_path=download_path)
        print(f"Video downloaded successfully to {os.path.join(download_path, video_stream.default_filename)}")
    
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # Get YouTube URL from the user
    video_url = input("Enter the YouTube video URL: ").strip()
    
    # Call the download function
    download_youtube_video(video_url)
