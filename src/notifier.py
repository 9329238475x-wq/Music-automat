"""
Music-Automat Executive Email Notification Module
Dispatches ultra-professional, VIP studio-grade dark-mode confirmation emails
to channel managers upon successful YouTube video upload.
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
DEFAULT_RECIPIENTS = ["9329238475x@gmail.com", "bamitbhai554@gmail.com"]
DEFAULT_APP_PASS = "ziqkkzjwffqnzrgn"


def send_upload_success_email(
    video_title: str,
    youtube_url: str,
    profile: str = "nagpuri",
    channel_name: str = "",
    duration_str: str = "2:30:00",
    track_count: int = 25,
    recipient_email: Optional[Any] = None
) -> bool:
    """
    Sends an ultra-professional, VIP dark-glassmorphic HTML confirmation email
    to both bamitbhai554@gmail.com and 9329238475x@gmail.com.
    """
    sender = os.environ.get("ALERT_GMAIL_SENDER") or DEFAULT_SENDER or "9329238475x@gmail.com"
    app_pass = os.environ.get("ALERT_GMAIL_APP_PASS") or DEFAULT_APP_PASS or "ziqkkzjwffqnzrgn"

    # Gather recipients
    if recipient_email:
        if isinstance(recipient_email, str):
            recipients = [r.strip() for r in recipient_email.split(",") if r.strip()]
        else:
            recipients = list(recipient_email)
    elif os.environ.get("ALERT_GMAIL_RECIPIENT"):
        recipients = [r.strip() for r in os.environ["ALERT_GMAIL_RECIPIENT"].split(",") if r.strip()]
    else:
        recipients = list(DEFAULT_RECIPIENTS)

    # Always ensure both requested addresses are included
    for req_addr in ["bamitbhai554@gmail.com", "9329238475x@gmail.com"]:
        if req_addr not in recipients:
            recipients.append(req_addr)

    # Deduplicate while preserving order
    unique_recipients = []
    for r in recipients:
        if r and r not in unique_recipients:
            unique_recipients.append(r)
    recipients_str = ", ".join(unique_recipients)

    if not app_pass:
        logger.warning("No Gmail App Password found. Skipping email notification.")
        return False

    now_ist = datetime.now().strftime("%d %b %Y, %I:%M %p")
    channel_display = channel_name.strip() if channel_name else f"{profile.capitalize()} DJ Channel"
    p_lower = profile.lower()

    if p_lower == "nagpuri":
        genre_badge = "THETH NAGPURI DJ"
        accent_color = "#ff7a00"
        gradient_header = "linear-gradient(135deg, #ff7a00 0%, #ffae00 100%)"
        accent_glow = "rgba(255, 122, 0, 0.35)"
    elif p_lower == "dj_nan_say_karwan":
        genre_badge = "STUDIO BEAT NAGPURI"
        accent_color = "#ff2a85"
        gradient_header = "linear-gradient(135deg, #ff2a85 0%, #9b00e8 100%)"
        accent_glow = "rgba(255, 42, 133, 0.35)"
    elif p_lower == "edm":
        genre_badge = "BHOJPURI EDM DROP"
        accent_color = "#d200ff"
        gradient_header = "linear-gradient(135deg, #d200ff 0%, #00f2fe 100%)"
        accent_glow = "rgba(210, 0, 255, 0.35)"
    else:
        genre_badge = "HARD VIBRATION DJ"
        accent_color = "#00e5ff"
        gradient_header = "linear-gradient(135deg, #00e5ff 0%, #7928ca 100%)"
        accent_glow = "rgba(0, 229, 255, 0.35)"

    video_id = youtube_url.split("v=")[-1].split("/")[-1].split("?")[0]
    watch_url = f"https://youtu.be/{video_id}"
    thumb_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

    subject = f"⚡ [PUBLISHED] {channel_display} | New Video Live on YouTube! 🎧"

    # Plain Text Fallback
    text_content = f"""
===================================================================
MUSIC-AUTOMAT STUDIO HUB | EXECUTIVE PRODUCTION REPORT
===================================================================
STATUS: VIDEO OFFICIALLY PUBLISHED & LIVE WORLDWIDE ON YOUTUBE!

CHANNEL      : {channel_display}
PROFILE      : {genre_badge}
VIDEO TITLE  : {video_title}
WATCH URL    : {watch_url}
VIDEO ID     : {video_id}
TOTAL TRACKS : {track_count} Songs (Seamless Nonstop Assembly)
TOTAL RUNTIME: {duration_str}
AUDIO MASTER : 320 kbps HD MP3 | EBU R128 (-14.0 LUFS) | Bass Boost +2.5dB
VISUALIZER   : 1080p Avee Player 360° Circular Bass Spectrum (Beat-Synced)
PUBLISHED AT : {now_ist} (IST)

WATCH DIRECTLY ON YOUTUBE:
{watch_url}

Dispatched to authorized channel managers: {recipients_str}
Automated production report by Music-Automat 24/7 Autonomous Studio Engine.
===================================================================
"""

    # Executive VIP Studio HTML Template
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>YouTube Release Report</title>
</head>
<body style="margin: 0; padding: 30px 10px; background-color: #080b12; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e2e8f0;">

  <!-- Main Container -->
  <table align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 640px; margin: 0 auto; background: #0f1422; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 20px; overflow: hidden; box-shadow: 0 25px 60px rgba(0, 0, 0, 0.85);">
    
    <!-- Top Header Bar -->
    <tr>
      <td style="padding: 26px 32px 20px; background: #0b0f1a; border-bottom: 1px solid rgba(255, 255, 255, 0.07); text-align: left;">
        <table width="100%" border="0" cellpadding="0" cellspacing="0">
          <tr>
            <td>
              <span style="display: inline-block; font-size: 11px; font-weight: 800; letter-spacing: 0.14em; text-transform: uppercase; color: {accent_color}; background: rgba(255, 255, 255, 0.05); padding: 5px 12px; border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.1);">
                ✦ MUSIC-AUTOMAT STUDIO HUB
              </span>
            </td>
            <td align="right">
              <span style="display: inline-block; font-size: 11px; font-weight: 700; color: #00ff88; background: rgba(0, 255, 136, 0.1); padding: 5px 12px; border-radius: 20px; border: 1px solid rgba(0, 255, 136, 0.3);">
                ● LIVE ON YOUTUBE
              </span>
            </td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- Hero Title Banner -->
    <tr>
      <td style="padding: 32px 32px 24px; text-align: left; background: radial-gradient(circle at top right, {accent_glow} 0%, rgba(15, 20, 34, 0) 65%);">
        <div style="font-size: 13px; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: {accent_color}; margin-bottom: 8px;">
          {genre_badge} &bull; PRODUCTION REPORT
        </div>
        <h1 style="margin: 0 0 10px; font-size: 26px; font-weight: 800; color: #ffffff; letter-spacing: -0.02em; line-height: 1.25;">
          🎉 Video Successfully Published!
        </h1>
        <p style="margin: 0; font-size: 14px; color: #94a3b8; line-height: 1.5;">
          Your autonomous DJ mix pipeline has finished rendering and is now publicly streaming worldwide on YouTube.
        </p>
      </td>
    </tr>

    <!-- Video Preview Card -->
    <tr>
      <td style="padding: 0 32px 28px;">
        <table width="100%" border="0" cellpadding="0" cellspacing="0" style="background: #141b2d; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 16px; overflow: hidden; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);">
          <!-- Thumbnail Image -->
          <tr>
            <td style="position: relative; text-align: center; background: #000000; padding: 0;">
              <a href="{watch_url}" target="_blank" style="display: block; text-decoration: none;">
                <img src="{thumb_url}" alt="Video Thumbnail" width="100%" style="display: block; max-height: 310px; object-fit: cover; border-bottom: 1px solid rgba(255, 255, 255, 0.08);" />
              </a>
            </td>
          </tr>
          <!-- Video Title & Watch Button -->
          <tr>
            <td style="padding: 22px 24px;">
              <div style="font-size: 11px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: #64748b; margin-bottom: 6px;">
                YOUTUBE RELEASE TITLE
              </div>
              <div style="font-size: 17px; font-weight: 700; color: #ffffff; line-height: 1.45; margin-bottom: 20px;">
                {video_title}
              </div>
              
              <!-- Direct CTA Button -->
              <table border="0" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td align="center">
                    <a href="{watch_url}" target="_blank" style="display: block; background: {gradient_header}; color: #ffffff !important; text-decoration: none; font-size: 15px; font-weight: 800; text-align: center; padding: 16px 28px; border-radius: 12px; box-shadow: 0 8px 24px {accent_glow}; letter-spacing: 0.02em;">
                      ▶&nbsp;&nbsp;WATCH DIRECTLY ON YOUTUBE
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- Technical Metrics Table -->
    <tr>
      <td style="padding: 0 32px 30px;">
        <table width="100%" border="0" cellpadding="0" cellspacing="0" style="background: #121828; border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 14px; overflow: hidden;">
          <tr>
            <td colspan="2" style="padding: 14px 20px; background: rgba(255, 255, 255, 0.03); border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 12px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: #94a3b8;">
              ⚡ PRODUCTION &amp; MASTERING SPECIFICATIONS
            </td>
          </tr>
          <tr>
            <td style="padding: 12px 20px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); font-size: 13px; color: #94a3b8; font-weight: 500;">Channel Identity</td>
            <td style="padding: 12px 20px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); font-size: 13px; color: #ffffff; font-weight: 700; text-align: right;">{channel_display}</td>
          </tr>
          <tr>
            <td style="padding: 12px 20px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); font-size: 13px; color: #94a3b8; font-weight: 500;">Total Compiled Tracks</td>
            <td style="padding: 12px 20px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); font-size: 13px; color: #ffffff; font-weight: 700; text-align: right;">{track_count} Fresh Tracks (Nonstop)</td>
          </tr>
          <tr>
            <td style="padding: 12px 20px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); font-size: 13px; color: #94a3b8; font-weight: 500;">Total Video Duration</td>
            <td style="padding: 12px 20px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); font-size: 13px; color: #ffffff; font-weight: 700; text-align: right;">{duration_str}</td>
          </tr>
          <tr>
            <td style="padding: 12px 20px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); font-size: 13px; color: #94a3b8; font-weight: 500;">Audio Mastering Quality</td>
            <td style="padding: 12px 20px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); font-size: 13px; color: #00ff88; font-weight: 700; text-align: right;">320 kbps HD &bull; EBU R128 (-14 LUFS)</td>
          </tr>
          <tr>
            <td style="padding: 12px 20px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); font-size: 13px; color: #94a3b8; font-weight: 500;">Visual Engine</td>
            <td style="padding: 12px 20px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); font-size: 13px; color: #ffffff; font-weight: 700; text-align: right;">1080p Avee Player 360° Spectrum</td>
          </tr>
          <tr>
            <td style="padding: 12px 20px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); font-size: 13px; color: #94a3b8; font-weight: 500;">Sub-Bass Calibration</td>
            <td style="padding: 12px 20px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); font-size: 13px; color: {accent_color}; font-weight: 700; text-align: right;">Sub-Bass Boosted +2.5dB</td>
          </tr>
          <tr>
            <td style="padding: 12px 20px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); font-size: 13px; color: #94a3b8; font-weight: 500;">YouTube Video ID</td>
            <td style="padding: 12px 20px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); font-size: 13px; color: #e2e8f0; font-family: monospace; font-weight: 700; text-align: right;">{video_id}</td>
          </tr>
          <tr>
            <td style="padding: 12px 20px; font-size: 13px; color: #94a3b8; font-weight: 500;">Published Timestamp</td>
            <td style="padding: 12px 20px; font-size: 13px; color: #ffffff; font-weight: 700; text-align: right;">{now_ist} (IST)</td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- Cloud Delivery Badge -->
    <tr>
      <td style="padding: 0 32px 30px;">
        <table width="100%" border="0" cellpadding="0" cellspacing="0" style="background: rgba(0, 229, 255, 0.05); border: 1px solid rgba(0, 229, 255, 0.15); border-radius: 12px; padding: 14px 18px;">
          <tr>
            <td width="30" valign="top" style="font-size: 18px; line-height: 1;">☁️</td>
            <td style="font-size: 12px; color: #94a3b8; line-height: 1.5;">
              <strong style="color: #ffffff;">Autonomous Cloud Execution:</strong> Headless multi-threaded rendering completed on 100% free cloud GPU runner. All temporary assets and scratch buffers have been automatically pruned.
            </td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- Footer -->
    <tr>
      <td style="padding: 24px 32px; background: #090c14; border-top: 1px solid rgba(255, 255, 255, 0.06); text-align: center;">
        <div style="font-size: 12px; color: #64748b; line-height: 1.6; margin-bottom: 8px;">
          Dispatched simultaneously to authorized channel managers:<br>
          <span style="color: #94a3b8; font-weight: 600;">{recipients_str}</span>
        </div>
        <div style="font-size: 11px; color: #475569;">
          Music-Automat 24/7 Autonomous Studio Engine &bull; Confidential Production Alert &bull; All Rights Reserved.
        </div>
      </td>
    </tr>

  </table>

</body>
</html>
"""

    recipients_str = ", ".join(unique_recipients)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Music-Automat Studio <{sender}>"
    msg["To"] = recipients_str

    part1 = MIMEText(text_content, "plain", "utf-8")
    part2 = MIMEText(html_content, "html", "utf-8")
    msg.attach(part1)
    msg.attach(part2)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender, app_pass)
            server.sendmail(sender, unique_recipients, msg.as_string())
        logger.info(f"Executive notification email dispatched successfully to: {recipients_str}")
        return True
    except Exception as exc:
        logger.error(f"Failed to dispatch executive email via SMTP: {exc}")
        return False


if __name__ == "__main__":
    ok = send_upload_success_email(
        video_title="🔥 Tor Bina Jina Mushkil Re X A Gori Tor Pyar Me Pagal - Nonstop Theth Nagpuri DJ Remix 2026 💃",
        youtube_url="https://youtu.be/dQw4w9WgXcQ",
        profile="nagpuri",
        channel_name="Nagpuri Non-Stop Remix 2.0",
        duration_str="2:45:10",
        track_count=25
    )
    print("Email sent status:", ok)
