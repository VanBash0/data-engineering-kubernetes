"""Split the original CSV without breaking quoted rows, then upload to S3."""

import argparse
import csv
import json
import os
import tempfile
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


def split_csv(source, directory, part_count):
    paths = [directory / f"part-{index}.csv" for index in range(part_count)]
    files = [path.open("w", encoding="utf-8", newline="") for path in paths]
    counts = [0] * part_count
    try:
        writers = [csv.writer(file) for file in files]
        with source.open("r", encoding="utf-8-sig", newline="") as input_file:
            reader = csv.reader(input_file)
            header = next(reader)
            for writer in writers:
                writer.writerow(header)
            for number, row in enumerate(reader):
                index = number % part_count
                writers[index].writerow(row)
                counts[index] += 1
    finally:
        for file in files:
            file.close()
    return paths, counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--parts", type=int, default=4)
    args = parser.parse_args()
    if args.parts < 2:
        parser.error("--parts must be at least 2")
    s3 = boto3.client(
        "s3", endpoint_url=os.environ["RUSTFS_ENDPOINT"],
        aws_access_key_id=os.environ["RUSTFS_ACCESS_KEY"],
        aws_secret_access_key=os.environ["RUSTFS_SECRET_KEY"],
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    try:
        s3.head_bucket(Bucket="vacancies")
    except ClientError as exc:
        if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 404:
            raise
        s3.create_bucket(Bucket="vacancies")
    with tempfile.TemporaryDirectory(prefix="hw5_parts_") as tmp:
        paths, counts = split_csv(args.source, Path(tmp), args.parts)
        for index, path in enumerate(paths):
            key = f"hw5/{args.run_id}/parts/part-{index}.csv"
            s3.upload_file(str(path), "vacancies", key)
            print(f"uploaded {key}: {counts[index]} rows, {path.stat().st_size} bytes", flush=True)
    manifest = {"run_id": args.run_id, "parts": args.parts,
                "total_rows": sum(counts), "rows_per_part": counts}
    s3.put_object(Bucket="vacancies", Key=f"hw5/{args.run_id}/parts/manifest.json",
                  Body=json.dumps(manifest).encode("utf-8"), ContentType="application/json")
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
