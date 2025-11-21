import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient } from '@aws-sdk/lib-dynamodb';

export const initializeDynamoClient = () => {
  const client = new DynamoDBClient({
    region: 'local',
    endpoint: 'http://localhost:3000/dynamodb',  // Full URL including the proxy path
    credentials: {
      accessKeyId: 'dummy',
      secretAccessKey: 'dummy'
    },
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': '*',
      'Access-Control-Allow-Methods': '*'
    }
  });

  return DynamoDBDocumentClient.from(client, {
    marshallOptions: {
      removeUndefinedValues: true,
    }
  });
}; 