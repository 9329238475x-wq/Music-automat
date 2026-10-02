"""
Email Notification Module for Music-Automat
Dispatches high-aesthetic dark-mode confirmation emails to user Gmail upon successful video upload.
"""

import os
import ssl
import smtplib
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, List, Dict, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Notifier")

DEFAULT_SENDER = "9329238475x@gmail.com"
DEFAULT_RECIPIENT = "9329238475x@gmail.com"
DEFAULT_APP_PASS = "ziqkkzjwffqnzrgn"


def send_upload_success_email(
    video_title: str,
    youtube_url: str,
    profile: str = "nagpuri",
    channel_name: str = "",
    duration_str: str = "2:30:00",
    track_count: int = 25,
    recipient_email: Optional[str] = None
) -> bool:
    """
    Sends a rich, responsive dark-mode HTML email confirmation to the user's Gmail.
    """
    sender = os.environ.get("ALERT_GMAIL_SENDER") or DEFAULT_SENDER or "9329238475x@gmail.com"
    app_pass = os.environ.get("ALERT_GMAIL_APP_PASS") or DEFAULT_APP_PASS or "ziqkkzjwffqnzrgn"
    recipient = recipient_email or os.environ.get("ALERT_GMAIL_RECIPIENT") or DEFAULT_RECIPIENT or "9329238475x@gmail.com"

    if not app_pass:
        logger.warning("No Gmail App Password found. Skipping email notification.")
        return False

    now_ist = datetime.now().strftime("%d %b %Y, %I:%M %p")
    channel_display = channel_name.strip() if channel_name else f"{profile.capitalize()} DJ Channel"
    genre_badge = "NAGPURI NORMAL DJ" if profile.lower() == "nagpuri" else "HARD VIBRATION DJ"
    accent_color = "#00e5ff" if profile.lower() == "nagpuri" else "#ff2a85"

    video_id = youtube_url.split("v=")[-1].split("/")[-1].split("?")[0]
    watch_url = f"https://youtu.be/{video_id}"

    subject = f"🎧 {channel_display} - Video Live on YouTube! | {video_title[:45]}"

    # Plain Text Fallback
    text_content = f"""
{channel_display.upper()} - VIDEO UPLOAD SUCCESSFUL!
======================================================
Channel       : {channel_display}
Profile       : {genre_badge}
Video Title   : {video_title}
Video Link    : {watch_url}
Total Tracks  : {track_count} Songs
Duration      : {duration_str}
Upload Time   : {now_ist} (IST)

Watch Now     : {watch_url}
======================================================
Automated notification from Music-Automat 24/7 Cloud Engine.
"""

    # High-Aesthetic Dark Glassmorphic HTML
    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>YouTube Upload Success</title>
  <style>
    body {{
      background-color: #07090e;
      color: #f0f4fc;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      margin: 0;
      padding: 30px 15px;
    }}
    .email-container {{
      max-width: 600px;
      margin: 0 auto;
      background: #101422;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 20px;
      overflow: hidden;
      box-shadow: 0 20px 60px rgba(0,0,0,0.9);
    }}
    .email-header {{
      background: linear-gradient(135deg, #0d1b2a 0%, #1b0c1e 100%);
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      padding: 30px 25px 22px;
      text-align: center;
    }}
    .brand-pill {{
      display: inline-block;
      background: {accent_color};
      color: #000000;
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      padding: 5px 14px;
      border-radius: 20px;
      margin-bottom: 12px;
    }}
    .header-title {{
      margin: 0;
      font-size: 24px;
      font-weight: 800;
      color: #ffffff;
      letter-spacing: -0.5px;
    }}
    .email-body {{
      padding: 30px 25px;
    }}
    .status-alert {{
      background: rgba(0, 255, 136, 0.12);
      border: 1px solid rgba(0, 255, 136, 0.35);
      border-radius: 12px;
      padding: 14px 18px;
      margin-bottom: 24px;
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .status-text {{
      color: #00ff88;
      font-size: 14px;
      font-weight: 700;
    }}
    .video-title-box {{
      background: rgba(0, 0, 0, 0.4);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 12px;
      padding: 18px;
      margin-bottom: 24px;
    }}
    .video-title-label {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #8b98b5;
      margin-bottom: 6px;
      font-weight: 700;
    }}
    .video-title-text {{
      font-size: 16px;
      color: #ffffff;
      font-weight: 700;
      line-height: 1.4;
      margin: 0;
    }}
    .info-card {{
      background: rgba(18, 22, 36, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 14px;
      padding: 18px 20px;
      margin-bottom: 26px;
    }}
    .field-row {{
      display: flex;
      justify-content: space-between;
      padding: 9px 0;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      font-size: 13px;
    }}
    .field-row:last-child {{
      border-bottom: none;
    }}
    .field-key {{
      color: #8b98b5;
      font-weight: 500;
    }}
    .field-val {{
      color: #ffffff;
      font-weight: 700;
      text-align: right;
    }}
    .cta-button {{
      display: block;
      background: linear-gradient(135deg, {accent_color}, #ff0055);
      color: #ffffff !important;
      text-decoration: none;
      font-weight: 800;
      font-size: 15px;
      text-align: center;
      padding: 16px 28px;
      border-radius: 12px;
      box-shadow: 0 6px 24px rgba(0, 229, 255, 0.3);
      margin-bottom: 18px;
    }}
    .cloud-notice {{
      background: rgba(0, 229, 255, 0.06);
      border: 1px solid rgba(0, 229, 255, 0.15);
      border-radius: 10px;
      padding: 12px 16px;
      font-size: 12px;
      color: #b9c7e2;
      line-height: 1.5;
    }}
    .email-footer {{
      padding: 20px 25px;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      text-align: center;
      font-size: 11px;
      color: #55627e;
      background: #0b0e18;
    }}
  </style>
</head>
<body>
  <div class="email-container">
    <div class="email-header">
      <span class="brand-pill">{genre_badge}</span>
      <h1 class="header-title">🎧 {channel_display}</h1>
      <div style="margin: 8px 0 0; font-size: 13px; color: #00ff88; font-weight: 600;">⚡ Video Live &amp; Published Successfully</div>
    </div>

    <div class="email-body">
      <div class="status-alert">
        <span style="font-size: 20px;">✅</span>
        <div class="status-text">Your Nonstop DJ Mix is now live on YouTube!</div>
      </div>

      <div class="video-title-box">
        <div class="video-title-label">Uploaded Video Title</div>
        <p class="video-title-text">{video_title}</p>
      </div>

      <div class="info-card">
        <div class="field-row">
          <span class="field-key">Channel Profile</span>
          <span class="field-val">{channel_display}</span>
        </div>
        <div class="field-row">
          <span class="field-key">Track Count</span>
          <span class="field-val">{track_count} Songs (Nonstop)</span>
        </div>
        <div class="field-row">
          <span class="field-key">Total Duration</span>
          <span class="field-val">{duration_str}</span>
        </div>
        <div class="field-row">
          <span class="field-key">Transitions</span>
          <span class="field-val" style="color:#00ff88;">Smooth 'Wooosh' Riser</span>
        </div>
        <div class="field-row">
          <span class="field-key">YouTube Video ID</span>
          <span class="field-val" style="font-family:monospace;color:{accent_color};">{video_id}</span>
        </div>
        <div class="field-row">
          <span class="field-key">Published Time</span>
          <span class="field-val">{now_ist}</span>
        </div>
      </div>

      <a href="{watch_url}" class="cta-button" target="_blank">
        ▶️ Watch Video on YouTube
      </a>

      <div class="cloud-notice">
        ☁️ <strong>100% Free Kaggle Cloud Run:</strong> Entire mix was compiled, rendered, and uploaded autonomously. All temp files cleaned up.
      </div>
    </div>

    <div class="email-footer">
      Music-Automat 24/7 Multi-Channel Cloud Engine &bull; System Alert to {recipient}
    </div>
  </div>
</body>
</html>
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Music-Automat Hub <{sender}>"
    msg["To"] = recipient

    part1 = MIMEText(text_content, "plain", "utf-8")
    part2 = MIMEText(html_content, "html", "utf-8")
    msg.attach(part1)
    msg.attach(part2)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender, app_pass)
            server.sendmail(sender, [recipient], msg.as_string())
        logger.info(f"Notification email dispatched successfully to {recipient}!")
        return True
    except Exception as exc:
        logger.error(f"Failed to dispatch email via SMTP: {exc}")
        return False


if __name__ == "__main__":
    ok = send_upload_success_email(
        video_title="NONSTOP NAGPURI DJ REMIX 2026 🔥 Test Notification",
        youtube_url="https://youtu.be/dQw4w9WgXcQ",
        profile="nagpuri",
        channel_name="RL REMIX RAJPUR 807",
        duration_str="2:45:10",
        track_count=25
    )
    print("Email sent status:", ok)
