"""Step 9 — Deliver: upload deck to Google Drive (converted to Google Slides), export a PDF,
and email the PPTX + PDF + Slides link via Gmail.

Usage: python tools/deliver.py [--date YYYY-MM-DD] [--to someone@example.com] [--no-email]
       python tools/deliver.py --alert "message"      # failure alert email (used by run_weekly)
"""
from __future__ import annotations

import base64
import html
import io
import sys
from email.message import EmailMessage
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from common import env, get_logger, load_config, parse_run_date_arg, read_json, run_dir, write_json
from google_auth import get_credentials

log = get_logger("deliver")
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def drive_folder(drive, name: str) -> str:
    q = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    found = drive.files().list(q=q, fields="files(id)", spaces="drive").execute().get("files", [])
    if found:
        return found[0]["id"]
    return drive.files().create(body={"name": name, "mimeType": "application/vnd.google-apps.folder"}, fields="id").execute()["id"]


def upload_and_convert(drive, pptx: Path, folder_id: str, title: str) -> tuple[str, str, bytes]:
    meta = {"name": title, "parents": [folder_id], "mimeType": "application/vnd.google-apps.presentation"}
    f = drive.files().create(body=meta, media_body=MediaFileUpload(str(pptx), mimetype=PPTX_MIME, resumable=True),
                             fields="id, webViewLink").execute()
    buf = io.BytesIO()
    req = drive.files().export_media(fileId=f["id"], mimeType="application/pdf")
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return f["id"], f["webViewLink"], buf.getvalue()


def send_email(gmail, to: str, subject: str, html_body: str, attachments: list[tuple[str, bytes, str]]):
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content("This report is best viewed as HTML. Open the attached deck or the Google Slides link.")
    msg.add_alternative(html_body, subtype="html")
    for name, data, mime in attachments:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    gmail.users().messages().send(userId="me", body={"raw": raw}).execute()


def email_html(ins: dict, m: dict, slides_url: str | None) -> str:
    e = html.escape
    bullets = "".join(f"<li style='margin-bottom:8px'><b>{e(t['headline'])}</b><br><span style='color:#555'>{e(t['detail'])}</span></li>"
                      for t in ins["exec_summary"])
    ideas = "".join(f"<li style='margin-bottom:6px'><b>{e(i['title'])}</b> <span style='color:#777'>({e(i['format'])})</span><br>"
                    f"<span style='color:#555'>{e(i['why_now'])}</span></li>" for i in ins["video_ideas"][:3])
    link = (f"<p><a href='{slides_url}' style='background:#6250d6;color:#fff;padding:10px 18px;border-radius:6px;"
            f"text-decoration:none;font-weight:bold'>Open the deck in Google Slides</a></p>") if slides_url else ""
    k = m["kpis"]
    return f"""<div style="font-family:Segoe UI,Arial,sans-serif;max-width:640px;color:#111">
<p style="color:#6250d6;font-weight:bold;letter-spacing:1px;font-size:12px">AI YOUTUBE PULSE · {e(m['run_date'])}</p>
<h2 style="margin:4px 0 8px">{e(ins['deck_headline'])}</h2>
<p style="color:#444">{e(ins['niche_mood'])}</p>
<p style="color:#777;font-size:13px">{k['videos_analyzed']:,} videos · {k['channels_tracked']} channels · {k['outliers_3x']} videos at 3x+ their channel norm</p>
{link}
<h3>This week's takeaways</h3><ul style="padding-left:18px">{bullets}</ul>
<h3>Top video ideas</h3><ol style="padding-left:18px">{ideas}</ol>
<p style="color:#999;font-size:12px">Full deck attached (PowerPoint + PDF). Generated automatically by your YouTube Analysis pipeline.</p>
</div>"""


def send_alert(text: str):
    creds = get_credentials(interactive=False)
    gmail = build("gmail", "v1", credentials=creds, cache_discovery=False)
    to = env("REPORT_EMAIL")
    send_email(gmail, to, "⚠ YouTube report pipeline failed",
               f"<pre style='font-family:Consolas,monospace'>{html.escape(text)}</pre>", [])


def main(run_date: str | None = None, to: str | None = None, email: bool = True) -> dict:
    cfg = load_config()
    out = run_dir(run_date)
    pptx = out / "deck.pptx"
    deck = read_json(out / "deck_data.json")
    ins, m = deck["insights"], deck["metrics"]
    title = f"{cfg['delivery']['subject_prefix']} — {m['run_date']}"

    creds = get_credentials(interactive=False)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    folder = drive_folder(drive, cfg["delivery"]["drive_folder_name"])
    file_id, slides_url, pdf = upload_and_convert(drive, pptx, folder, title)
    (out / "deck.pdf").write_bytes(pdf)
    log.info("Uploaded to Drive: %s", slides_url)

    result = {"slides_url": slides_url, "drive_file_id": file_id}
    if email:
        gmail = build("gmail", "v1", credentials=creds, cache_discovery=False)
        to = to or env("REPORT_EMAIL")
        fname = f"AI-YouTube-Pulse-{m['run_date']}"
        send_email(gmail, to, f"{title}: {ins['deck_headline']}", email_html(ins, m, slides_url),
                   [(f"{fname}.pptx", pptx.read_bytes(), PPTX_MIME), (f"{fname}.pdf", pdf, "application/pdf")])
        log.info("Email sent")
        result["emailed"] = True
    write_json(out / "delivery.json", result)
    return result


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--alert" in args:
        send_alert(args[args.index("--alert") + 1])
    else:
        to = args[args.index("--to") + 1] if "--to" in args else None
        main(parse_run_date_arg(args), to=to, email="--no-email" not in args)
