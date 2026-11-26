"""Map one CSV shard or reduce all shard results from in-cluster S3."""

import argparse
import csv
import io
import itertools
import json
import os
from collections import Counter
from pathlib import Path

from selection import is_python_developer


BUCKET = "vacancies"


def parse_skills(raw):
    return sorted({part.strip().lower() for part in (raw or "").split(";") if part.strip()})


def count_pairs(reader):
    counts = Counter()
    total = selected = 0
    for row in csv.DictReader(reader):
        total += 1
        if not is_python_developer(row):
            continue
        selected += 1
        counts.update(itertools.combinations(parse_skills(row.get("key_skills")), 2))
    return total, selected, counts


def records(counts):
    return [{"items": list(items), "count": count}
            for items, count in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]


def s3_client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3", endpoint_url=os.environ["RUSTFS_ENDPOINT"],
        aws_access_key_id=os.environ["RUSTFS_ACCESS_KEY"],
        aws_secret_access_key=os.environ["RUSTFS_SECRET_KEY"],
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def read_json(s3, key):
    response = s3.get_object(Bucket=BUCKET, Key=key)
    try:
        return json.load(response["Body"])
    finally:
        response["Body"].close()


def write_json(s3, key, value):
    payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
    s3.put_object(Bucket=BUCKET, Key=key, Body=payload, ContentType="application/json")


def map_part(s3, run_id, index):
    key = f"hw5/{run_id}/parts/part-{index}.csv"
    response = s3.get_object(Bucket=BUCKET, Key=key)
    try:
        reader = io.TextIOWrapper(response["Body"], encoding="utf-8-sig", newline="")
        total, selected, counts = count_pairs(reader)
    finally:
        response["Body"].close()
    result = {"part": index, "total_rows": total,
              "selected_vacancies": selected, "pairs": records(counts)}
    write_json(s3, f"hw5/{run_id}/partials/part-{index}.json", result)
    print(f"part={index} rows={total} selected={selected} unique_pairs={len(counts)}", flush=True)


def reduce_parts(s3, run_id, part_count):
    counts = Counter()
    total = selected = 0
    for index in range(part_count):
        part = read_json(s3, f"hw5/{run_id}/partials/part-{index}.json")
        if part["part"] != index:
            raise ValueError(f"Unexpected shard index: {part['part']}")
        total += part["total_rows"]
        selected += part["selected_vacancies"]
        counts.update({tuple(record["items"]): record["count"] for record in part["pairs"]})
    pairs = records(counts)
    expected = json.loads(Path("/app/reference/top10_pairs.json").read_text(encoding="utf-8"))
    result = {"source": f"s3://{BUCKET}/hw5/{run_id}/parts/",
              "total_rows": total, "selected_vacancies": selected,
              "unique_pairs": len(pairs), "top10": pairs[:10],
              "matches_hw3_top10": pairs[:10] == expected}
    write_json(s3, f"hw5/{run_id}/results/pairs.json", pairs)
    write_json(s3, f"hw5/{run_id}/results/summary.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    if total != 229388 or selected != 5608 or len(pairs) != 34184 or not result["matches_hw3_top10"]:
        raise ValueError("Kubernetes result does not match homework 3")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("map", "reduce"))
    args = parser.parse_args()
    run_id = os.environ["RUN_ID"]
    s3 = s3_client()
    if args.mode == "map":
        index = int(os.environ["JOB_COMPLETION_INDEX"])
        map_part(s3, run_id, index)
    else:
        reduce_parts(s3, run_id, int(os.environ["PART_COUNT"]))
    try:
        import resource
        print(f"peak_rss_mib={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.2f}", flush=True)
    except ImportError:
        pass


if __name__ == "__main__":
    main()
