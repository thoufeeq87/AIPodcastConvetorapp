import streamlit as st
from pydub import AudioSegment
from deepgram import DeepgramClient, PrerecordedOptions, FileSource
import requests
import re
import zipfile
from io import BytesIO
import os

# Access secrets
deepgram_api_key = st.secrets["deepgram_api_key"]
openai_api_key = st.secrets["openai_api_key"]

# Streamlit application title
st.title("Podcast to Audiobook Converter")

# Initialize session state
if 'conversion_status' not in st.session_state:
    st.session_state.conversion_status = ""
if 'uploaded_file' not in st.session_state:
    st.session_state.uploaded_file = None
if 'output_prefix' not in st.session_state:
    st.session_state.output_prefix = "output_audiobook"
if 'audiobook_script' not in st.session_state:
    st.session_state.audiobook_script = ""

# File uploader for MP3 files
uploaded_file = st.file_uploader("Upload your podcast MP3 file", type="mp3")
if uploaded_file:
    st.session_state.uploaded_file = uploaded_file

# Text input for naming the output audiobook file
output_prefix = st.text_input("Enter the output audiobook file name (without extension)", "output_audiobook")
st.session_state.output_prefix = output_prefix

# Display conversion status
st.write(st.session_state.conversion_status)

def convert_mp3_to_wav(mp3_file_path, wav_file_path):
    audio = AudioSegment.from_mp3(mp3_file_path)
    audio.export(wav_file_path, format="wav")

def transcribe_audio(audio_file_path):
    deepgram = DeepgramClient(deepgram_api_key)
    with open(audio_file_path, 'rb') as audio:
        buffer_data = audio.read()
    payload: FileSource = {"buffer": buffer_data}
    options = PrerecordedOptions(model="nova-2", smart_format=True)
    try:
        response = deepgram.listen.prerecorded.v("1").transcribe_file(payload, options, timeout=600)
        transcript = response["results"]["channels"][0]["alternatives"][0]["transcript"]
        with open("transcript.txt", "w") as file:
            file.write(transcript)
        return transcript
    except KeyError:
        st.error("Error: 'results' not found in Deepgram response.")
        return None
    except Exception as e:
        st.error(f"Exception: {e}")
        return None

def format_transcript(transcript):
    if transcript is None:
        return ""
    return re.sub(r'\s+', ' ', transcript).strip()

def generate_audiobook_script(transcript):
    if not transcript:
        return ""
    prompt = f"""Task: Create a high-quality audiobook script from the provided transcripts. Follow the specific format outlined below to ensure a professional and engaging final product. Each section should be a minimum of 500 words to ensure depth and engagement. While the provided examples illustrate the format, you are not required to follow them strictly; instead, adhere to the format structure and provide natural pauses to make the script easier to listen to.

Format Details:

Title and Introduction

Opening Credits: Include the title, author, and narrator.
Introduction: Provide a brief introduction to set the stage for the listener.
Example:
Welcome to "The Adventure of a Lifetime" by John Doe, narrated by Jane Smith. In this thrilling tale, you will embark on a journey filled with unexpected twists and turns. Let's begin.

Chapters

Chapter Announcement: Clearly state the chapter number and title.
Content: Read the chapter content clearly and engagingly.
Transitions: Use natural pauses to indicate transitions between sections or major points. For short pauses, use "," or ".". For longer pauses, use ". . .". Each chapter must include a mandatory long pause using ". . .".
Example:
Chapter One: The Beginning
It was a dark and stormy night when Emily first arrived in the small town of Willow Creek. The rain pounded against the car windows, creating a rhythmic beat that mirrored her racing heart.

Mid-Book Announcements

Optional Announcements: Provide updates or additional information, such as acknowledgments or mid-book summaries.
Example:
This concludes Chapter Five. Stay tuned for Chapter Six, where Emily's adventure takes an unexpected turn.

Chapter Endings

Clear Ending: Indicate the end of each chapter with a pause.
Example:
And with that, Emily knew her journey was far from over. She had only just begun to uncover the secrets of Willow Creek.

Conclusion

Closing Remarks: Provide a brief conclusion or closing remarks.
Closing Credits: Mention the title, author, narrator, and any other pertinent information.
Example:
And so, Emily's story comes to a close, leaving us with the promise of new adventures on the horizon. Thank you for listening to "The Adventure of a Lifetime" by John Doe, narrated by Jane Smith. This audiobook was produced by XYZ Productions. We hope you enjoyed the journey.

Instructions: Utilize the provided transcripts to create a cohesive and engaging audiobook script only following the format above. Each section should be at least 500 words to ensure a comprehensive presentation. Use natural pauses to enhance the listening experience—short pauses can be indicated with "," or ".", and longer pauses with ". . .". Each chapter must include a mandatory long pause using ". . .". Ensure each section is clearly defined and transitions smoothly to maintain the listener's interest and provide a professional listening experience. Do not use music in the audiobook script and avoid using the word "podcast."

Transcript:
[{transcript}]
"""
    response = requests.post(
        'https://api.openai.com/v1/chat/completions',
        headers={'Authorization': f'Bearer {openai_api_key}', 'Content-Type': 'application/json'},
        json={'model': 'gpt-3.5-turbo', 'messages': [{'role': 'system', 'content': 'You are a helpful assistant.'}, {'role': 'user', 'content': prompt}], 'max_tokens': 3500, 'temperature': 0.7}
    )
    response_data = response.json()
    if 'choices' not in response_data:
        st.error("Error: 'choices' not found in OpenAI response.")
        return ""
    return response_data['choices'][0]['message']['content'].strip()

def text_to_speech(text, output_audio_file_prefix):
    if not text:
        st.error("Error: No text provided for text-to-speech conversion.")
        return
    max_chunk_size = 2000  # Maximum character limit for Deepgram
    chunks = [text[i:i + max_chunk_size] for i in range(0, len(text), max_chunk_size)]
    api_url = 'https://api.deepgram.com/v1/speak'
    headers = {'Authorization': f'Token {deepgram_api_key}', 'Content-Type': 'application/json'}
    audio_files = []
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
    if audio_files:
        combined_audio = AudioSegment.from_file(audio_files[0])
        for audio_file in audio_files[1:]:
            audio_segment = AudioSegment.from_file(audio_file)
            combined_audio += audio_segment
        combined_audio.export(f"{output_audio_file_prefix}.wav", format="wav")
        st.success(f'Audiobook content written to "{output_audio_file_prefix}.wav"')
    else:
        st.error("Error: No audio segments created.")

def create_zip_and_download():
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        zip_file.writestr("audiobook_script.txt", st.session_state.audiobook_script)
        zip_file.write(f"{st.session_state.output_prefix}.wav")
    zip_buffer.seek(0)
    st.download_button(
        label="Download All Files",
        data=zip_buffer,
        file_name=f"{st.session_state.output_prefix}_files.zip",
        mime="application/zip"
    )

# Start conversion process
if st.session_state.uploaded_file and st.button("Start Conversion"):
    st.session_state.conversion_status = "Conversion in process..."
    mp3_file_path = "temp_podcast.mp3"
    with open(mp3_file_path, "wb") as f:
        f.write(st.session_state.uploaded_file.getbuffer())
    convert_mp3_to_wav(mp3_file_path, f"{st.session_state.output_prefix}.wav")
    transcript = transcribe_audio(f"{st.session_state.output_prefix}.wav")
    if transcript:
        formatted_transcript = format_transcript(transcript)
        st.session_state.audiobook_script = generate_audiobook_script(formatted_transcript)
        with st.spinner("Converting to audiobook..."):
            text_to_speech(st.session_state.audiobook_script, st.session_state.output_prefix)
            with open("audiobook_script.txt", "w") as file:
                file.write(st.session_state.audiobook_script)
            create_zip_and_download()
    else:
        st.error("Error in transcription. Please try again.")
else:
    if st.session_state.uploaded_file:
        st.write("Upload and start conversion.")
