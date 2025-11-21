import boto3

dynamodb = boto3.client('dynamodb', endpoint_url='http://localhost:8001', region_name='us-west-2')

def create_table(name, key_schema, attr_definitions, gsis=[]):
    try:
        params = {
            "TableName": name,
            "KeySchema": key_schema,
            "AttributeDefinitions": attr_definitions,
            "BillingMode": 'PAY_PER_REQUEST'
        }

        if gsis:
            params["GlobalSecondaryIndexes"] = gsis

        dynamodb.create_table(**params)
        print(f"✅ Created table: {name}")

    except dynamodb.exceptions.ResourceInUseException:
        print(f"⚠️ Table already exists: {name}")


# Table 1: career_wrestler
create_table(
    "career_wrestler",
    key_schema=[{"AttributeName": "career_id", "KeyType": "HASH"}],
    attr_definitions=[{"AttributeName": "career_id", "AttributeType": "S"}]
)

# Table 2: season_wrestler
create_table(
    "season_wrestler",
    key_schema=[{"AttributeName": "season_wrestler_id", "KeyType": "HASH"}],
    attr_definitions=[
        {"AttributeName": "season_wrestler_id", "AttributeType": "S"},
        {"AttributeName": "career_id", "AttributeType": "S"},
        {"AttributeName": "team_id", "AttributeType": "S"},
        {"AttributeName": "season", "AttributeType": "N"},
    ],
    gsis=[
        {
            "IndexName": "career_id-index",
            "KeySchema": [{"AttributeName": "career_id", "KeyType": "HASH"}],
            "Projection": {"ProjectionType": "ALL"},
            "ProvisionedThroughput": {
                "ReadCapacityUnits": 5,
                "WriteCapacityUnits": 5
            }
        },
        {
            "IndexName": "season_team-index",
            "KeySchema": [
                {"AttributeName": "season", "KeyType": "HASH"},
                {"AttributeName": "team_id", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        }
    ]
)

# Table 3: teams
create_table(
    "teams",
    key_schema=[{"AttributeName": "team_id", "KeyType": "HASH"}],
    attr_definitions=[{"AttributeName": "team_id", "AttributeType": "S"}]
)

# Table 4: team_seasons
create_table(
    "team_seasons",
    key_schema=[
        {"AttributeName": "team_id", "KeyType": "HASH"},
        {"AttributeName": "season", "KeyType": "RANGE"}
    ],
    attr_definitions=[
        {"AttributeName": "team_id", "AttributeType": "S"},
        {"AttributeName": "season", "AttributeType": "N"}
    ]
)

# Table 5: matches
create_table(
    "matches",
    key_schema=[{"AttributeName": "match_id", "KeyType": "HASH"}],
    attr_definitions=[
        {"AttributeName": "match_id", "AttributeType": "S"},
        {"AttributeName": "wrestler1_id", "AttributeType": "S"},
        {"AttributeName": "weight", "AttributeType": "S"}
    ],
    gsis=[
        {
            "IndexName": "match_wrestler-index",
            "KeySchema": [{"AttributeName": "wrestler1_id", "KeyType": "HASH"}],
            "Projection": {"ProjectionType": "ALL"},
            "ProvisionedThroughput": {
                "ReadCapacityUnits": 5,
                "WriteCapacityUnits": 5
            }
        }
    ]
)


# Table 6: career_link
create_table(
    "career_link",
    key_schema=[{"AttributeName": "season_wrestler_id", "KeyType": "HASH"}],
    attr_definitions=[{"AttributeName": "season_wrestler_id", "AttributeType": "S"}]
)
