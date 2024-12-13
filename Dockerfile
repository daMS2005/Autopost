FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# Install FFmpeg
RUN apt-get update && apt-get install -y ffmpeg

# Copy the requirements file into the container
COPY requirements.txt ./

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Command to run your script
CMD ["python", "reddit_doc.py"]