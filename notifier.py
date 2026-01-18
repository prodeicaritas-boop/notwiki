import os
import json
import smtplib
import glob
from email.message import EmailMessage
import config
from utils import setup_logger

logger = setup_logger("Notifier", os.path.join(config.LOGS_DIR, "notifier.log"))

def get_latest_two_files(directory):
    """Returns the two most recent JSON files in the directory."""
    files = sorted(glob.glob(os.path.join(directory, "*.json")))
    if not files:
        return None, None
    if len(files) == 1:
        return files[0], None
    return files[-1], files[-2]

def count_new_links(latest_file, previous_file):
    """Compares two JSON files and returns the count of new unique IDs."""
    try:
        with open(latest_file, 'r') as f:
            latest_data = json.load(f)

        # Flatten structure to get set of IDs
        latest_ids = set()
        for cat, items in latest_data.items():
            for item in items:
                latest_ids.add(item.get('unique_id'))

        if not previous_file:
            return len(latest_ids)

        with open(previous_file, 'r') as f:
            prev_data = json.load(f)

        prev_ids = set()
        for cat, items in prev_data.items():
            for item in items:
                prev_ids.add(item.get('unique_id'))

        new_links = latest_ids - prev_ids
        return len(new_links)

    except Exception as e:
        logger.error(f"Error comparing files: {e}")
        return 0

def check_errors():
    """Checks if the error log has content."""
    if os.path.exists(config.ERROR_LOG):
        if os.path.getsize(config.ERROR_LOG) > 0:
            with open(config.ERROR_LOG, 'r') as f:
                return f.read()
    return None

def send_email(subject, body):
    """Sends an email notification."""
    sender = config.EMAIL_SENDER
    password = config.EMAIL_PASSWORD
    receiver = config.EMAIL_RECEIVER

    if not all([sender, password, receiver]):
        logger.warning("Email credentials not set. Skipping notification.")
        return

    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = receiver

    try:
        # Assuming Gmail or standard SMTP
        # Adjust server/port if needed. 587 is standard TLS.
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)
        server.quit()
        logger.info("Email notification sent successfully.")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")

def main():
    logger.info("Starting notification check...")

    # 1. Check for New Links
    latest, previous = get_latest_two_files(config.DAILY_DATA_DIR)
    if not latest:
        logger.warning("No data files found.")
        return

    new_link_count = count_new_links(latest, previous)
    logger.info(f"New links found: {new_link_count}")

    # 2. Check for Errors
    error_content = check_errors()
    if error_content:
        logger.info("Critical errors found in log.")

    # 3. Decision Logic
    if new_link_count > 0 or error_content:
        subject = f"FMHY Scraper Report - {new_link_count} New Links"
        body = f"Scraper Run Complete.\n\nNew Links Found: {new_link_count}\n"

        if error_content:
            subject += " [ERRORS DETECTED]"
            body += "\n--- ERRORS ---\n" + error_content
        else:
            body += "\nNo critical errors reported."

        send_email(subject, body)
    else:
        logger.info("No significant changes or errors. No email sent.")

if __name__ == "__main__":
    main()
