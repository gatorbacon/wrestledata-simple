import boto3
import json
from decimal import Decimal
from boto3.dynamodb.types import TypeDeserializer

dynamodb = boto3.resource('dynamodb', endpoint_url='http://localhost:8001')
table = dynamodb.Table('matches')

# Helper function to convert Decimals to float or int
def clean_decimal(obj):
    if isinstance(obj, list):
        return [clean_decimal(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: clean_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    else:
        return obj

def backup_all_items():
    items = []
    scan_kwargs = {}
    done = False
    start_key = None

    while not done:
        if start_key:
            scan_kwargs['ExclusiveStartKey'] = start_key
        response = table.scan(**scan_kwargs)
        items.extend(response['Items'])
        start_key = response.get('LastEvaluatedKey', None)
        done = start_key is None

    clean_items = clean_decimal(items)

    with open('matches_backup.json', 'w') as f:
        json.dump(clean_items, f, indent=2)

    print(f"✅ Backed up {len(items)} matches to matches_backup.json")

if __name__ == "__main__":
    backup_all_items()