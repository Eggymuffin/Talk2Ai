Download the zip and extract it to a folder.

Do: python -m venv venv and activate the venv
activate using .\venv\Scripts\activate

Do: pip install -r requirements.txt

You can run the application by using: python answer_phone.py

Run ngrok: ngrok http 5000

Put the link ngrok gives you into the Twilio webhook under manage > active numbers > configure

Now you can call your Twilio number and talk to your own AI assistant!

