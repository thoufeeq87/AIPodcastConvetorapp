import os

# Set environment variables for ffmpeg and ffprobe
os.environ['FFMPEG_BINARY'] = '/usr/local/bin/ffmpeg'
os.environ['FFPROBE_BINARY'] = '/usr/local/bin/ffprobe'

import streamlit as st
from pydub import AudioSegment
from deepgram import DeepgramClient, PrerecordedOptions, FileSource
import requests
import re
import zipfile
from io import BytesIO

# Access secrets
deepgram_api_key = st.secrets["deepgram_api_key"]
openai_api_key = st.secrets["openai_api_key"]

# Streamlit application title
st.title("Podcast to Audiobook Converter")

# Instructional text for beginners
st.markdown("""
Welcome to the **Podcast to Audiobook Converter**! This tool will guide you through converting a podcast MP3 file into an audiobook. 
Simply upload your MP3 file, and the app will handle the rest, including transcription, text formatting, and audio conversion.
""")

# File uploader for MP3 files
uploaded_file = st.file_uploader("Upload your podcast MP3 file", type="mp3")

# Text input for naming the output audiobook file
output_prefix = st.text_input("Enter the output audiobook file name (without extension)", "output_audiobook")

# Convert button to trigger the process
if st.button("Convert Podcast to Audiobook"):
    if uploaded_file is not None:
        # Save the uploaded MP3 file
        mp3_file_path = f"temp_podcast.mp3"
        with open(mp3_file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # Display progress
        st.write("Conversion in process...")

        # Step 1: Convert MP3 to WAV
        def convert_mp3_to_wav(mp3_file_path, wav_file_path):
            audio = AudioSegment.from_mp3(mp3_file_path)
            audio.export(wav_file_path, format="wav")
            st.write(f"Converted {mp3_file_path} to {wav_file_path}")

        # Step 2: Transcribe the Podcast Audio to Text using Deepgram
        def transcribe_audio(audio_file_path):
            deepgram = DeepgramClient(deepgram_api_key)

            with open(audio_file_path, 'rb') as audio:
                buffer_data = audio.read()

            payload: FileSource = {"buffer": buffer_data}

            options = PrerecordedOptions(
                model="nova-2",
                smart_format=True,
            )

            try:
                # Show progress bar for transcription
                progress_bar = st.progress(0)
                response = deepgram.listen.prerecorded.v("1").transcribe_file(payload, options, timeout=600)
                progress_bar.progress(50)  # Update progress

                transcript = response["results"]["channels"][0]["alternatives"][0]["transcript"]

                # Save transcript to a file
                with open("transcript.txt", "w") as file:
                    file.write(transcript)

                progress_bar.progress(100)  # Complete progress
                return transcript
            except KeyError:
                st.error("Error: 'results' not found in Deepgram response.")
                st.write(response)
                return None
            except Exception as e:
                st.error(f"Exception: {e}")
                return None

        # Step 3: Format the Transcribed Text
        def format_transcript(transcript):
            if transcript is None:
                return ""
            # Remove any unwanted characters or symbols
            transcript = re.sub(r'\s+', ' ', transcript)
            return transcript.strip()

        # Step 4: Generate the Audiobook Script using OpenAI
        def generate_audiobook_script(transcript):
            if not transcript:
                return ""
            prompt = f"""Create a high-quality audiobook script from the provided podcast transcripts. Follow the specific format outlined below to ensure a professional and engaging final product. The Number of words should be minimum of 2000 words and maximum of 6000 words.

Format Details:
1. Title and Introduction
Opening Credits: Include the title, author, and narrator.
Introduction: Provide a brief introduction to set the stage for the listener.

Example:
[Opening Music]
Narrator: Welcome to "The Adventure of a Lifetime" by John Doe, narrated by Jane Smith.
[Music fades]
Narrator: In this thrilling tale, you will embark on a journey filled with unexpected twists and turns. Let's begin.

2. Chapters
Chapter Announcement: Clearly state the chapter number and title.
Content: Read the chapter content clearly and engagingly.
Transitions: Use pauses or brief music to indicate transitions between sections or major points.

Example:
Narrator: Chapter One: The Beginning
[Short pause]
Narrator: It was a dark and stormy night when Emily first arrived in the small town of Willow Creek. The rain pounded against the car windows, creating a rhythmic beat that mirrored her racing heart.

3. Mid-Book Announcements
Optional Announcements: Provide updates or additional information, such as acknowledgments or mid-book summaries.

Example:
Narrator: This concludes Chapter Five. Stay tuned for Chapter Six, where Emily's adventure takes an unexpected turn.
[Short pause with music]

4. Chapter Endings
Clear Ending: Indicate the end of each chapter with a pause or brief music.

Example:
Narrator: And with that, Emily knew her journey was far from over. She had only just begun to uncover the secrets of Willow Creek.
[Short pause]

5. Conclusion
Closing Remarks: Provide a brief conclusion or closing remarks.
Closing Credits: Mention the title, author, narrator, and any other pertinent information.
Closing Music: End with music to signify the end of the audiobook.

Example:
Narrator: And so, Emily's story comes to a close, leaving us with the promise of new adventures on the horizon. Thank you for listening to "The Adventure of a Lifetime" by John Doe, narrated by Jane Smith.
[Closing music fades in]
Narrator: This audiobook was produced by XYZ Productions. We hope you enjoyed the journey.
[Music fades out]

Instructions: Utilize the provided podcast transcripts to create a cohesive and engaging audiobook script following the format above. Ensure each section is clearly defined and transitions smoothly to maintain the listener's interest and provide a professional listening experience.

Podcast Transcript:
[{transcript}]"""

            response = requests.post(
                'https://api.openai.com/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {openai_api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'gpt-3.5-turbo',
                    'messages': [
                        {'role': 'system', 'content': 'You are a helpful assistant.'},
                        {'role': 'user', 'content': prompt}
                    ],
                    'max_tokens': 3500,
                    'temperature': 0.7
                }
            )
            response_data = response.json()
            if 'choices' not in response_data:
                st.error("Error: 'choices' not found in OpenAI response.")
                st.write(response_data)
                return ""
            return response_data['choices'][0]['message']['content'].strip()

        # Step 5: Convert Text to Speech using Deepgram
        def text_to_speech(text, output_audio_file_prefix):
            if not text:
                st.error("Error: No text provided for text-to-speech conversion.")
                return

            max_chunk_size = 2000  # Maximum character limit for Deepgram
            chunks = [text[i:i + max_chunk_size] for i in range(0, len(text), max_chunk_size)]

            api_url = 'https://api.deepgram.com/v1/speak'
            headers = {
                'Authorization': f'Token {deepgram_api_key}',
                'Content-Type': 'application/json'
            }

            audio_files = []
            total_chunks = len(chunks)
            for i, chunk in enumerate(chunks):
                try:
                    data = {'text': chunk}
                    response = requests.post(api_url, headers=headers, json=data)

                    if response.status_code == 200:
                        if 'audio/mpeg' in response.headers.get('Content-Type', ''):
                            audio_file_path = f"{output_audio_file_prefix}_chunk_{i + 1}.mp3"
                            with open(audio_file_path, 'wb') as audio_file:
                                audio_file.write(response.content)
                            audio_files.append(audio_file_path)
                        else:
                            st.error(f"Unexpected content type: {response.headers.get('Content-Type')}")
                    else:
                        st.error(f"Exception for chunk {i + 1}: {response.status_code} - {response.text}")
                except Exception as e:
                    st.error(f"Exception for chunk {i + 1}: {e}")

            # Combine all audio files into one
            if audio_files:
                combined_audio = AudioSegment.from_file(audio_files[0])
                for audio_file in audio_files[1:]:
                    audio_segment = AudioSegment.from_file(audio_file)
                    combined_audio += audio_segment
                combined_audio.export(f"{output_audio_file_prefix}.wav", format="wav")
                st.success(f'Audiobook content written to "{output_audio_file_prefix}.wav"')
            else:
                st.error("Error: No audio segments created.")

        # Zip and download all files
        def create_zip_and_download():
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
                zip_file.write("transcript.txt")
                zip_file.write(f"{output_prefix}.wav")

            zip_buffer.seek(0)
            st.download_button(
                label="Download All Files",
                data=zip_buffer,
                file_name=f"{output_prefix}_files.zip",
                mime="application/zip"
            )

        # Putting It All Together
        def convert_podcast_to_audiobook(mp3_file_path, audiobook_output_prefix):
            st.write("Conversion in process...")
            # Step 1: Convert MP3 to WAV
            podcast_audio_wav_path = "podcast_audio.wav"
            convert_mp3_to_wav(mp3_file_path, podcast_audio_wav_path)

            # Step 2: Transcribe the podcast audio to text
            st.write("Transcription of podcast is in process...")
            transcript = transcribe_audio(podcast_audio_wav_path)
            if transcript is None:
                st.error("Transcription failed. Exiting...")
                return
            st.write("Transcription of podcast is complete.")

            # Step 3: Format the transcribed text
            formatted_text = format_transcript(transcript)
            st.write("Text formatting complete.")

            # Step 4: Generate the audiobook script
            st.write("Audiobook Script is under process...")
            audiobook_script = generate_audiobook_script(formatted_text)
            if not audiobook_script:
                st.error("Audiobook script generation failed.")
                return
            st.write("Audiobook script is completed.")

            # Step 5: Convert the audiobook script to audio
            text_to_speech(audiobook_script, audiobook_output_prefix)
            st.write("Audiobook is ready and you can download.")

            # Create zip and download all files
            create_zip_and_download()

        # Run the conversion process
        convert_podcast_to_audiobook(mp3_file_path, output_prefix)
    else:
        st.error("Please upload an MP3 file to continue.")
