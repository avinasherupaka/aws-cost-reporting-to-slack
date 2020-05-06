#!/bin/bash

export SlackNotificationToken=$1

#Suggest deploying to us-east-1 due to CE API
export AWS_DEFAULT_REGION=us-east-1 
#Change the below, an s3 bucket to store lambda code for deploy, and output report
#Must be in same region as lambda (ie AWS_DEFAULT_REGION)
export BUCKET=obp-aws-cost-explorer-FILL_WITH_AWS_ACCOUNT_NUMBER

#Comma Seperated list of Cost Allocation Tags (must be configured in AWS billing prefs)
export COST_TAGS=mon:cost-center
#Do you want partial figures for the current month (set to true if running weekly/daily)
export CURRENT_MONTH=true
#Day of Month, leave as 6 unless you want to capture refunds and final support values, then change to 12
export DAY_MONTH=6

cd ./src
zip -ur -X ../bin/lambda.zip lambda.py
cd ..

SNS_ARN=`aws cloudformation describe-stacks --stack-name obp-cf-notifier | jq ".Stacks[].Outputs[].OutputValue"  | tr -d '"'`

aws cloudformation package \
   --template-file src/sam.yaml \
   --output-template-file deploy.sam.yaml \
   --s3-bucket $BUCKET \
   --s3-prefix obp-aws-cost-explorer-report-builds
aws cloudformation deploy \
   --template-file deploy.sam.yaml \
   --stack-name obp-aws-cost-explorer-report \
   --tags mon:env=non-prod mon:regulated=no mon:cost-center=5180-9115-PSC80003 mon:data-classification=restricted mon:owner=OBP-AWS-ADMIN mon:project=OBP \
   --capabilities CAPABILITY_NAMED_IAM \
   --notification-arns $SNS_ARN \
   --parameter-overrides SlackNotificationToken=$SlackNotificationToken S3Bucket=$BUCKET \
   AccountLabel=Name ListOfCostTags=$COST_TAGS CurrentMonth=$CURRENT_MONTH \
   DayOfMonth=$DAY_MONTH
