from flask import Flask, request, redirect, url_for, render_template
import os
from werkzeug.utils import secure_filename
import threading
from flask_socketio import SocketIO, emit
import azure.cognitiveservices.speech as speechsdk
from transcribe import vid_to_aud, summarize, sendmail

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'mp4', 'mov', 'avi', 'mkv'}
socketio = SocketIO(app)
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

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
         # Creating the JSON object to emit
        json_data = {
            'speaker_id': evt.result.speaker_id,
            'text': evt.result.text
        }
        # Emitting the JSON object with the speaker_id and text
        socketio.emit('transcription_update', json_data)

    def handle_canceled(evt):
        nonlocal done
        print(f'CANCELED: Reason={evt.reason}')
        if evt.reason == speechsdk.CancellationReason.Error:
            print(f'ErrorDetails={evt.error_details}')
        done = True
        socketio.emit('transcription_complete', broadcast=True)

    def handle_session_stopped(evt):
        nonlocal done
        print('Session stopped event.')
        done = True
        socketio.emit('transcription_complete', broadcast=True)

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
    full_transcription = '\n'.join([f'{speaker}: {text}' for speaker, text in transcription])
    print("Full transcription with speaker differentiation:")
    print(full_transcription)
    return full_transcription

def process(path, email, length):
    audio_path = vid_to_aud(path)
    transcript = transcribe_audio(audio_path)
    summary = summarize(transcript, length)
    sendmail(transcript, summary, email)
    os.remove(path)
    os.remove(audio_path)

@app.route('/')
def upload_form():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_video():
    if 'file' not in request.files:
        return "No file part"
    file = request.files['file']
    email = request.form['email']
    summary_length = request.form['summary']
    if file.filename == '':
        return "No selected file"
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        threading.Thread(target=process, args=(filepath, email, summary_length)).start()
        return redirect(url_for('processing'))

@app.route('/processing')
def processing():
    return render_template('processing.html')

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
