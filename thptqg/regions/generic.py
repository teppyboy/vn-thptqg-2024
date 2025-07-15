import csv
import logging
import json
import threading
from time import sleep
from pathlib import Path
from datetime import datetime
from requests import Session
from paddleocr import PaddleOCR

REGIONS = {
    "01": "https://tracuu.hanoi.edu.vn/",
    "04": "https://tradiem.khaothicaobang.edu.vn/2018",
    "08": "http://tn2018.tuyenquang.edu.vn",
    "11": "https://tradiem2018.dienbien.edu.vn/",
    "12": "http://tracuudiem2018.laichau.edu.vn",
    "14": "http://tracuudiemthi.sogddtsonla.edu.vn/",
    "15": "http://diemthi.laocai.edu.vn/",
    "19": "https://diemthi.thainguyen.edu.vn/",
    "20": "https://langson.edu.vn/tra-cuu/diem-thi-tn-thpt-2025",
    "22": "https://gdqn.edu.vn/diemtn",
    "24": "http://diemthi2018.bacninh.edu.vn/",
    "25": "https://tradiem.phutho.edu.vn/",
    "31": "https://diemthi.haiphong.edu.vn/",
    "33": "http://diemthi.hungyen.edu.vn",
    "37": "https://ninhbinh.edu.vn/tra-cuu/bang-diem",
    "38": "http://thitn.thanhhoa.edu.vn:8281/",
    "40": "http://nghean.edu.vn/_diem-thi-tn-thpt-nam-2025-ct-2018",
    "42": "http://tracuudiemthi.hatinh.edu.vn/",
    "44": "https://diemthi.quangtri.edu.vn/",
    "46": "http://tracuudiem2.thuathienhue.edu.vn:81/",
    "48": "https://tracuudiem.danang.edu.vn",
    "51": "https://diemthi.quangngai.edu.vn/",
    "52": "",
    "56": "http://diemthi.khanhhoa.edu.vn/",
    "66": "https://diemthi.daklak.edu.vn",
    "68": "https://diemthilamdong.vnptschool.com.vn/",
    "75": "https://tracuudiem.dongnai.edu.vn/",
    "79": "https://diemthi.hcm.edu.vn/2018",
    "80": "",
    "82": "http://tracuudiem2.dongthap.edu.vn",
    "86": "http://tracuudiem.vinhlong.edu.vn",
    "91": "https://tracuu.angiang.edu.vn/",
    "92": "https://diemthithpt.ctu.edu.vn/",
    "96": "http://diemthithpt.camau.edu.vn/"
}
TMP_DIR = Path("./tmp/")
TMP_DIR.mkdir(exist_ok=True)
DATA_DIR = Path("./data/")
DATA_DIR.mkdir(exist_ok=True)
logger = logging.getLogger("thptqg.regions.generic")


def ocr_captcha(ocr: PaddleOCR, session: Session, host: str) -> str | None:
    current_timestamp = int(datetime.now().timestamp() * 1000)
    captcha_rsp = session.get(
        f"{host}/TraCuu/GetCaptcha?time={current_timestamp}&choose=1"
    )
    captcha_img_path = TMP_DIR.joinpath(f"{current_timestamp}.png")
    with open(captcha_img_path, "wb") as f:
        f.write(captcha_rsp.content)
    ocr_attempts = 2
    captcha_text: str | None = None
    captcha_confidence = None
    while ocr_attempts > 0:
        captcha_result = ocr.ocr(str(captcha_img_path), cls=True)
        logger.info(f"OCR result: {captcha_result}")
        try:
            captcha_text = captcha_result[0][0][1][0]
            captcha_confidence = captcha_result[0][0][1][1]
            if len(captcha_text) < 5: # type: ignore
                raise IndexError
        except (IndexError, TypeError):
            ocr_attempts -= 1
            continue
        break

    logger.info(f"Captcha text / Confidence: {captcha_text} / {captcha_confidence}")
    Path(captcha_img_path).unlink()
    return captcha_text


def tra_cuu(session: Session, host: str, region_id: int, sbd: int, captcha_text: str):
    data = {"SOBAODANH": str(region_id).zfill(2) + str(sbd).zfill(6), "ConfirmCode": captcha_text}
    tra_cuu_rsp = session.post(f"{host}/TraCuu/TraCuu", data=data)
    if tra_cuu_rsp.status_code == 500:
        return None
    try:
        return tra_cuu_rsp.json()
    except json.JSONDecodeError:
        return None


def run_region(ocr: PaddleOCR, session: Session, region_id: str):
    host = REGIONS.get(region_id)
    if not host:
        logger.error(f"Region ID '{region_id}' not found in REGIONS.")
        return
    student_id = 1
    file = DATA_DIR.joinpath(f"generic_{region_id}.csv")
    if file.exists():
        try:
            with file.open("r") as f:
                student_id = int(f.readlines()[-1].split(",")[0]) + 1
        except (IndexError, ValueError):
            logger.warning(f"[{region_id}] Failed to read last student ID from {file}, starting from 1.")
            student_id = 1
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
    ]
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    if not file.exists():
        writer.writeheader()
    while True:
        student_attempt = 0
        logger.info(f"[{region_id}] Finding student info for '{student_id}'")
        captcha_text = ocr_captcha(ocr, session, host)
        if captcha_text is None:
            logger.error(f"[{region_id}] Failed to OCR captcha, retrying...")
            continue
        tra_cuu_rsp = tra_cuu(session, host, int(region_id), student_id, captcha_text)
        if (
            tra_cuu_rsp is None
            or tra_cuu_rsp.get("Message") == "Không tìm thấy thí sinh"
        ):
            student_id += 1
            if student_id < 2000:
                logger.info(f"[{region_id}] Student not found, retrying...")
                continue
            else:
                if student_attempt > 9:
                    break
                student_attempt += 1
                continue
        if tra_cuu_rsp.get("Message") == "Hiện chưa đến thời điểm tra cứu Điểm thi, Thí sinh vui lòng quay lại sau.":
            logger.error(f"[{region_id}] Not yet time to check scores, exiting...")
            return
        if tra_cuu_rsp.get("Message") == "Mã xác nhận không hợp lệ":
            logger.info(f"[{region_id}] Invalid captcha, retrying...")
            continue
        logger.info(f"[{region_id}] Found student info for '{student_id}'")
        logger.info(f"[{region_id}] Response: {tra_cuu_rsp}")
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
        }
        all_score_str = tra_cuu_rsp.get("DIEM_THI")
        if all_score_str is None:
            continue
        while all_score_str.strip() != "":
            logger.info(f"[{region_id}] All score (raw string): {all_score_str}")
            subject = all_score_str.split(":")[0].strip()
            score_str = all_score_str.split(":")[1].strip().split(" ")[0].strip()
            score = float(score_str)
            logger.info(f"[{region_id}] Subject: %s, Score: %s", subject, score)
            if subject not in ["KHTN", "KHXH"]:
                try:
                    score_dict[subject] = score
                except KeyError:
                    logger.warning(f"[{region_id}] Unknown subject '{subject}' found, skipping...")
            all_score_str = (
                all_score_str.removeprefix(subject + ":")
                .strip()
                .removeprefix(score_str)
                .strip()
            )
        writer.writerow(score_dict)
        logger.info(f"[{region_id}] Saved student info for '{student_id}'")
        student_id += 1
        student_attempt = 0
        sleep(0.4)

def run(ocr: PaddleOCR, session: Session):
    for region_id in REGIONS.keys():
        logger.info(f"Running region {region_id}...")
        threading.Thread(
            target=run_region,
            args=(ocr, session, region_id),
            name=f"Region-{region_id}",
            daemon=True
        ).start()
    # Wait for all threads to finish
    while threading.active_count() > 1:
        sleep(1)
    logger.info("All regions completed.")
