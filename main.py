import os
import json
import requests
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
import database
import models
import google.generativeai as genai
from apscheduler.schedulers.background import BackgroundScheduler

# সেফ প্লেসহোল্ডার (রেন্ডারে এনভায়রনমেন্ট ভেরিয়েবল থেকে পড়বে)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "YOUR_META_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "1246133088592613")

if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
    genai.configure(api_key=GEMINI_API_KEY)

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Yaadki WhatsApp AI Assistant - Live", version="2.5")

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_and_send_reminders():
    db = database.SessionLocal()
    try:
        pending_reminders = db.query(models.Reminder).filter(models.Reminder.status == "pending").all()
        for rem in pending_reminders:
            url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
            headers = {
                "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                "Content-Type": "application/json"
            }
            alert_text = f"⏰ রিমাইন্ডার অ্যালার্ট!\n📌 টাস্ক: {rem.task_description}\nসময় হয়ে গেছে!"
            payload = {
                "messaging_product": "whatsapp",
                "to": rem.phone_number,
                "type": "text",
                "text": {"body": alert_text}
            }
            res = requests.post(url, headers=headers, json=payload)
            if res.status_code == 200:
                rem.status = "sent"
                db.commit()
    except Exception as e:
        print("Scheduler error:", e)
    finally:
        db.close()

scheduler = BackgroundScheduler()
scheduler.add_job(check_and_send_reminders, 'interval', minutes=1)
scheduler.start()

@app.get("/")
def home():
    return {"status": "Yaadki AI Cloud Backend is live!"}

@app.get("/reminders")
def get_all_reminders(db: Session = Depends(get_db)):
    return db.query(models.Reminder).all()

@app.get("/webhook")
def verify_whatsapp_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    if mode == "subscribe" and token == "yaadki_secure_token":
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Verification token mismatch")

@app.post("/webhook")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    
    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                
                for msg in messages:
                    phone = msg.get("from")
                    msg_body = msg.get("text", {}).get("body")
                    
                    if not phone or not msg_body:
                        continue
                        
                    parsed_task = msg_body
                    assigned_time = "নির্ধারিত সময়ে"

                    try:
                        prompt = f"""
                        Analyze the following message in Bengali, Banglish, or English and extract the task description and reminder time.
                        Message: "{msg_body}"
                        Return a JSON object with keys: "task" (string) and "reminder_time" (string, clear readable format in Bengali).
                        Return ONLY valid JSON.
                        """
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        response = model.generate_content(prompt, generation_config={ "response_mime_type": "application/json" })
                        parsed_data = json.loads(response.text)
                        parsed_task = parsed_data.get("task", msg_body)
                        assigned_time = parsed_data.get("reminder_time", "নির্ধারিত সময়ে")
                    except Exception as e:
                        print("Gemini Error:", e)

                    new_reminder = models.Reminder(
                        phone_number=phone,
                        task_description=parsed_task,
                        reminder_time=assigned_time,
                        status="pending"
                    )
                    db.add(new_reminder)
                    db.commit()
                    db.refresh(new_reminder)

                    reply_text = f"✅ আপনার রিমাইন্ডার সফলভাবে সেভ হয়েছে!\n📌 টাস্ক: {parsed_task}\n⏰ সময়: {assigned_time}"
                    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
                    headers = {
                        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "messaging_product": "whatsapp",
                        "to": phone,
                        "type": "text",
                        "text": {"body": reply_text}
                    }
                    requests.post(url, headers=headers, json=payload)
                              
    except Exception as e:
        print(f"Error processing webhook: {e}")

    return {"status": "success"}
