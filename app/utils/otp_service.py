import os
import random
import string
from datetime import datetime, timedelta
from app import db
from app.models.user import OTPRecord


class OTPService:
    OTP_EXPIRY_MINUTES = 10

    @staticmethod
    def generate_otp(length=6):
        return "".join(random.choices(string.digits, k=length))

    @staticmethod
    def create_otp(phone: str) -> str:
        # Invalidate any existing OTPs
        OTPRecord.query.filter_by(phone=phone, is_used=False).update({"is_used": True})
        db.session.commit()

        otp_code = OTPService.generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=OTPService.OTP_EXPIRY_MINUTES)

        otp_record = OTPRecord(phone=phone, otp_code=otp_code, expires_at=expires_at)
        db.session.add(otp_record)
        db.session.commit()

        return otp_code

    @staticmethod
    def verify_otp(phone: str, otp_code: str) -> bool:
        record = (
            OTPRecord.query.filter_by(phone=phone, otp_code=otp_code, is_used=False)
            .order_by(OTPRecord.created_at.desc())
            .first()
        )

        if not record or not record.is_valid():
            return False

        record.is_used = True
        db.session.commit()
        return True

    @staticmethod
    def send_otp(phone: str) -> bool:
        """Send OTP via Twilio SMS. Returns True on success."""
        otp_code = OTPService.create_otp(phone)

        twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
        twilio_phone = os.environ.get("TWILIO_PHONE_NUMBER")

        if not all([twilio_sid, twilio_token, twilio_phone]):
            # In dev mode without Twilio configured, just log the OTP
            print(f"[DEV] OTP for {phone}: {otp_code}")
            return True

        try:
            from twilio.rest import Client
            client = Client(twilio_sid, twilio_token)
            client.messages.create(
                body=f"Your Tumana verification code is: {otp_code}. Valid for {OTPService.OTP_EXPIRY_MINUTES} minutes.",
                from_=twilio_phone,
                to=phone,
            )
            return True
        except Exception as e:
            print(f"[ERROR] Failed to send OTP to {phone}: {e}")
            return False
