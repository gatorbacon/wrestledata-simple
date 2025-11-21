# scripts/clear_matches.py

import boto3

dynamodb = boto3.resource('dynamodb', endpoint_url='http://localhost:8001')
table = dynamodb.Table('matches')

print("📦 Scanning and deleting all matches...")

deleted = 0
scan_kwargs = {}
while True:
    response = table.scan(**scan_kwargs)
    items = response.get('Items', [])
    for item in items:
        table.delete_item(Key={'match_id': item['match_id']})
        deleted += 1

    # Check for pagination
    if 'LastEvaluatedKey' in response:
        scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
    else:
        break

print(f"🧹 Deleted {deleted} matches from the table.")
