import boto3

DB = boto3.resource('dynamodb', endpoint_url='http://localhost:8001')

# Tables to clear
tables = ['career_wrestler', 'season_wrestler', 'career_link', 'matches']

def wipe_table(table_name):
    table = DB.Table(table_name)
    print(f"🧹 Wiping table: {table_name}")
    scan = table.scan()
    items = scan.get('Items', [])

    with table.batch_writer() as batch:
        for item in items:
            # Build key dict from key schema
            key = {k['AttributeName']: item[k['AttributeName']] for k in table.key_schema}
            batch.delete_item(Key=key)

    print(f"✅ Cleared {len(items)} items from {table_name}\n")

if __name__ == '__main__':
    for t in tables:
        wipe_table(t)

    print("🎯 All specified tables cleared.")
