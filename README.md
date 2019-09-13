## AWS Cost Explorer Report Generator

Python SAM Lambda module for generating an Excel cost report with graphs, including month on month cost changes. Uses the AWS Cost Explorer API for data.

![screenshot](https://github.com/aws-samples/aws-cost-explorer-report/blob/master/screenshot.png)

## AWS Costs

* AWS Lambda Invocation 
  * Usually [Free](https://aws.amazon.com/free/)  
* Amazon SES 
  * Usually [Free](https://aws.amazon.com/free/)
* Amazon S3
  * Minimal usage
* AWS Cost Explorer API calls   
  * [$0.01 per API call (about 25 calls per run)](https://aws.amazon.com/aws-cost-management/pricing/)

## RUN

`sh deploy.sh`