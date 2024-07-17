import importlib
import logging
import requests
import thptqg.constants as constants
from pathlib import Path
from paddleocr import PaddleOCR


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s (%(funcName)s) (%(filename)s:%(lineno)d) [%(levelname)s]: %(message)s",
)
logger = logging.getLogger("thptqg")


def main():
    logger.setLevel("INFO")
    logger.info("Initializing AI model...")
    ocr = PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False)
    logger.info("Initializing session...")
    session = requests.Session()
    session.headers.update({"User-Agent": constants.USER_AGENT})
    logger.info("Running regions...")
    for region_path in Path.cwd().joinpath("thptqg/regions").iterdir():
        region = region_path.stem
        if region == "__pycache__":
            continue
        logger.info(f"Running region {region}...")
        module = importlib.import_module(f"thptqg.regions.{region}")
        module.run(ocr, session)
    logger.info("Done.")


if __name__ == "__main__":
    main()
