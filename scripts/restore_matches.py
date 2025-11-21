import boto3
import json
from decimal import Decimal

dynamodb = boto3.resource('dynamodb', endpoint_url='http://localhost:8001')
table = dynamodb.Table('matches')

# Recursively convert floats/ints back to Decimal
def convert_to_decimal(obj):
    if isinstance(obj, list):
        return [convert_to_decimal(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, float) or isinstance(obj, int):
        return Decimal(str(obj))
    else:
        return obj

with open('matches_backup.json') as f:
    raw_items = json.load(f)

items = [convert_to_decimal(item) for item in raw_items]

# Batch write (max 25 items at a time)
with table.batch_writer(overwrite_by_pkeys=['match_id']) as batch:
    for i, item in enumerate(items):
        batch.put_item(Item=item)
        if (i + 1) % 10000 == 0:
            print(f"Uploaded {i + 1} matches...")

print(f"✅ Restored {len(items)} matches to the new matches table")