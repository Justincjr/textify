import azure.cognitiveservices.speech as speechsdk
import os
from dotenv import load_dotenv
from moviepy.editor import VideoFileClip
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from openai import AzureOpenAI
from email.mime.base import MIMEBase
from email import encoders
load_dotenv()

# Convert video to audio
def vid_to_aud(path):
    video = VideoFileClip(path)
    audio_path = os.path.splitext(path)[0] + ".wav"
    video.audio.write_audiofile(audio_path)
    video.close()
    return audio_path

# Azure Speech configuration
speech_key = os.getenv('key')
service_region = os.getenv('region')

def transcribe_audio(file_path):
    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
    audio_input = speechsdk.AudioConfig(filename=file_path)
    transcriber = speechsdk.transcription.ConversationTranscriber(speech_config=speech_config, audio_config=audio_input)

    transcription = []
    def handle_transcribed(evt):
        print(f'Transcribed: {evt.result.text}')
        transcription.append((evt.result.speaker_id, evt.result.text))
        
    def handle_canceled(evt):
        nonlocal done
        print(f'CANCELED: Reason={evt.reason}')
        if evt.reason == speechsdk.CancellationReason.Error:
            print(f'ErrorDetails={evt.error_details}')
        done = True

    def handle_session_stopped(evt):
        nonlocal done
        print('Session stopped event.')
        done = True

    # Connect callbacks to the events fired by the transcriber.
    transcriber.transcribed.connect(handle_transcribed)
    transcriber.canceled.connect(handle_canceled)
    transcriber.session_stopped.connect(handle_session_stopped)

    # Start continuous transcription.
    print("Starting continuous transcription with speaker differentiation...")
    transcriber.start_transcribing_async()

    # Wait until transcription is done.
    done = False
    while not done:
        # This sleep prevents the loop from consuming too much CPU.
        import time
        time.sleep(0.1)

    # Stop transcription.
    print("Stopping continuous transcription...")
    transcriber.stop_transcribing_async().get()
    print("Stopped.")

    # Concatenate the transcription list into a readable format with speaker IDs.
    full_transcription = '\n'.join([f'Speaker {speaker}: {text}' for speaker, text in transcription])
    print("Full transcription with speaker differentiation:")
    print(full_transcription)
    return full_transcription

def summarize(input, length):
    client = AzureOpenAI(
        api_key=os.getenv('api_key'),  
        api_version="2024-02-01",
        azure_endpoint = os.getenv('azure_endpoint')
    )  
    deployment_name=os.getenv('deployment')
    sys_msg="Assistant is an intelligent chatbot designed to summarize transcripts"
    if length == 1:
        sys_msg= sys_msg + "Your task is to summarize the transcript in a sentence"
    if length == 2:
        sys_msg= sys_msg + "Your task is to summarize the transcript in a paragraph"
    if length == 3:
        sys_msg= sys_msg + "Your task is to give a detailed summary of the transcription"
    try:
        response = client.chat.completions.create(model=deployment_name,
                                        messages=[{"role": "system", "content": sys_msg},
                                            {"role": "user", "content": input}
                                            ])
        output = response.choices[0].message.content
        print(output)
        return output
    except Exception as e:
        print(e)
        return ""

def sendmail(transcript, summary, receiver_email):
    print("Function sendmail started")
    sender_email = os.getenv('sender_email')

    # Define the email subject and body
    subject = 'Transcript'
    body = 'Summary: ' + summary

    # Create a MIMEMultipart object
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject

    # Attach the email body to the MIME message
    msg.attach(MIMEText(body, 'plain'))

    # Write the transcript to a temporary text file
    transcript_filename = 'transcript.txt'
    with open(transcript_filename, 'w') as f:
        f.write(transcript)
    
    # Attach the transcript file to the email
    with open(transcript_filename, 'rb') as attachment:
        mime_base = MIMEBase('application', 'octet-stream')
        mime_base.set_payload(attachment.read())
        encoders.encode_base64(mime_base)
        mime_base.add_header('Content-Disposition', f'attachment; filename={transcript_filename}')
        msg.attach(mime_base)

    # Define the SMTP server and port for Gmail
    smtp_server = 'smtp.gmail.com'
    smtp_port = 587

    # Define your email account credentials
    email_username = os.getenv('email_username')
    print(email_username)
    email_password = os.getenv('email_password')

    try:
        # Connect to the SMTP server
        print("Connecting to the SMTP server...")
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.ehlo()
        server.starttls()  # Upgrade the connection to a secure encrypted SSL/TLS connection
        server.ehlo()
        print("Starting TLS...")

        # Login to the SMTP server
        print("Logging in to the SMTP server...")
        server.login(email_username, email_password)

        # Send the email
        print("Sending email...")
        server.sendmail(sender_email, receiver_email, msg.as_string())
        print('Email sent successfully!')

    except Exception as e:
        print(f'Failed to send email: {e}')

    finally:
        # Terminate the SMTP session and close the connection
        print("Quitting the server...")
        server.quit()
        os.remove(transcript_filename)