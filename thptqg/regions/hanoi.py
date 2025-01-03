import csv
import logging
import json
from time import sleep
from pathlib import Path
from datetime import datetime
from requests import Session
from paddleocr import PaddleOCR

HOST = "https://api-tracuudiem.thitotnghiepthpt.edu.vn"
TMP_DIR = Path("./tmp/")
TMP_DIR.mkdir(exist_ok=True)
DATA_DIR = Path("./data/")
DATA_DIR.mkdir(exist_ok=True)
logger = logging.getLogger("thptqg.regions.hanoi")


def ocr_captcha(ocr: PaddleOCR, session: Session) -> str:
    current_timestamp = int(datetime.now().timestamp() * 1000)
    captcha_rsp = session.get(f"{HOST}/Captcha/GetCaptchaImage")
    captcha_rsp.raise_for_status()
    captcha_img_path = TMP_DIR.joinpath(f"{current_timestamp}.jpg")
    with open(captcha_img_path, "wb") as f:
        f.write(captcha_rsp.content)
    ocr_attempts = 2
    captcha_text = None
    captcha_confidence = None
    while ocr_attempts > 0:
        captcha_result = ocr.ocr(str(captcha_img_path), cls=True)
        logger.info(f"OCR result: {captcha_result}")
        try:
            captcha_text = captcha_result[0][0][1][0]
            captcha_confidence = captcha_result[0][0][1][1]
            if len(captcha_text) < 5:
                raise IndexError
        except (IndexError, TypeError):
            ocr_attempts -= 1
            continue
        break

    logger.info(f"Captcha text / Confidence: {captcha_text} / {captcha_confidence}")
    Path(captcha_img_path).unlink()
    return captcha_text


def tra_cuu(session: Session, sbd: int, captcha_text: str):
    # Hanoi region is 01
    query = {"SBD": "01" + str(sbd).zfill(6), "CaptchaValue": captcha_text}
    tra_cuu_rsp = session.get(f"{HOST}/Search_Score_/GetStudentMark", params=query)
    if tra_cuu_rsp.status_code == 500:
        return None
    try:
        return tra_cuu_rsp.json()
    except json.JSONDecodeError:
        return tra_cuu_rsp.text


def run(ocr: PaddleOCR, session: Session):
    student_id = 1
    file = DATA_DIR.joinpath("hanoi.csv")
    if file.exists():
        with file.open("r") as f:
            student_id = int(f.readlines()[-1].split(",")[0]) + 1
        csvfile = file.open("a", newline="")
    else:
        csvfile = file.open("w", newline="")
    fieldnames = [
        "SBD",
        "Toán",
        "Ngữ văn",
        "Tiếng Anh",
        "Vật lí",
        "Hóa học",
        "Sinh học",
        "Lịch sử",
        "Địa lí",
        "GDCD",
        "Tiếng Nga",
        "Tiếng Pháp",
        "Tiếng Trung",
        "Tiếng Đức",
        "Tiếng Nhật",
        "Tiếng Hàn",
    ]
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    if not file.exists():
        writer.writeheader()
    while True:
        student_attempt = 0
        logger.info(f"Finding student info for '{student_id}'")
        captcha_text = ocr_captcha(ocr, session)
        tra_cuu_rsp = tra_cuu(session, student_id, captcha_text)
        if tra_cuu_rsp is None or isinstance(tra_cuu_rsp, dict):
            print(tra_cuu_rsp)
            student_id += 1
            if student_id < 2000:
                logger.info("Student not found, retrying...")
                continue
            else:
                if student_attempt > 9:
                    break
                student_attempt += 1
                continue
        if isinstance(tra_cuu_rsp, dict) and tra_cuu_rsp.get("ErrorMessage") in [
            "Mã xác nhận không khớp",
            "Y\u00EAu c\u1EA7u kh\u00F4ng h\u1EE3p l\u1EC7: M\u00E3 x\u00E1c nh\u1EADn kh\u00F4ng kh\u1EDBp",
        ]:
            logger.info("Invalid captcha, retrying...")
            continue
        logger.info(f"Found student info for '{student_id}'")
        logger.info("Parsing student info...")
        score_dict = {
            "SBD": str(student_id).zfill(6),
            "Toán": None,
            "Ngữ văn": None,
            "Tiếng Anh": None,
            "Vật lí": None,
            "Hóa học": None,
            "Sinh học": None,
            "Lịch sử": None,
            "Địa lí": None,
            "GDCD": None,
            "Tiếng Nga": None,
            "Tiếng Pháp": None,
            "Tiếng Trung": None,
            "Tiếng Đức": None,
            "Tiếng Nhật": None,
            "Tiếng Hàn": None,
        }
        all_score_str = tra_cuu_rsp
        if all_score_str is None:
            continue
        while all_score_str.strip() != "":
            logger.info(f"All score (raw string): {all_score_str}")
            subject = all_score_str.split(":")[0].strip()
            score_str = all_score_str.split(":")[1].strip().split(" ")[0].strip()
            score = float(score_str)
            logger.info("Subject: %s, Score: %s", subject, score)
            if subject not in ["KHTN", "KHXH"]:
                score_dict[subject] = score
            all_score_str = (
                all_score_str.removeprefix(subject + ":")
                .strip()
                .removeprefix(score_str)
                .strip()
            )
        writer.writerow(score_dict)
        logger.info(f"Saved student info for '{student_id}'")
        student_id += 1
        student_attempt = 0
        sleep(0.4)
