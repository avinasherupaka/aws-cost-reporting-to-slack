#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2019 Bayer or its affiliates. All Rights Reserved.
# 
# Author: Avinash Erupaka

"""
Cost Explorer Report

A script, for local or lambda use, to generate CostExplorer excel graphs and post file to slack

"""

from __future__ import print_function

__author__ = "Avinash Erupaka"
__version__ = "1.0.0"
__license__ = "MIT No Attribution"

import os
import sys
# Required to load modules from vendored subfolder (for clean development env)
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "./vendored"))

import boto3
import datetime
import logging
import pandas as pd
#For date
from dateutil.relativedelta import relativedelta
#For Slack
from slacker import Slacker


#GLOBALS
CURRENT_MONTH = os.environ.get('CURRENT_MONTH')
if CURRENT_MONTH == "true":
    CURRENT_MONTH = True
else:
    CURRENT_MONTH = False

LAST_MONTH_ONLY = os.environ.get("LAST_MONTH_ONLY")

#Default exclude support, as for Enterprise Support
#as support billing is finalised later in month so skews trends    
INC_SUPPORT = os.environ.get('INC_SUPPORT')
if INC_SUPPORT == "true":
    INC_SUPPORT = True
else:
    INC_SUPPORT = False

TAG_VALUE_FILTER = os.environ.get('TAG_VALUE_FILTER') or '*'
TAG_KEY = os.environ.get('TAG_KEY')

class CostExplorer:
    """Retrieves BillingInfo checks from CostExplorer API
    >>> costexplorer = CostExplorer()
    >>> costexplorer.addReport(GroupBy=[{"Type": "DIMENSION","Key": "SERVICE"}])
    >>> costexplorer.generateExcel()
    """    
    def __init__(self, CurrentMonth=False):
        #Array of reports ready to be output to Excel.
        self.reports = []
        self.client = boto3.client('ce', region_name='us-east-1')
        self.end = datetime.date.today().replace(day=1)
        self.riend = datetime.date.today()
        if CurrentMonth or CURRENT_MONTH:
            self.end = self.riend

        if LAST_MONTH_ONLY:
            self.start = (datetime.date.today() - relativedelta(months=+1)).replace(day=1) #1st day of month a month ago
        else:
            # Default is last 12 months
            self.start = (datetime.date.today() - relativedelta(months=+12)).replace(day=1) #1st day of month 12 months ago
    
        self.ristart = (datetime.date.today() - relativedelta(months=+11)).replace(day=1) #1st day of month 11 months ago
        self.sixmonth = (datetime.date.today() - relativedelta(months=+6)).replace(day=1) #1st day of month 6 months ago, so RI util has savings values
        try:
            self.accounts = self.getAccounts()
        except:
            logging.exception("Getting Account names failed")
            self.accounts = {}

    if not "SlackNotificationToken" in os.environ.keys():
        print("""Environment variable SlackNotificationToken is not defined.
        This environment variable is used to obtain the token for sending Slack
        notifications. Please define it and run again.
        """)
        exit(2)
    slack_token = os.environ["SlackNotificationToken"]
    # slack client
    slack = Slacker(slack_token)        
    
    # Slack 
    def notify(self, message):
        self.slack.chat.post_message(channel="#obp-product-it", text=message)

    def upload_to_slack(self, file, ftype="auto"):
        basename = os.path.basename(file)
        print("environ Account ID on Function main " + os.environ['CURRENT_ACCOUNT_ID'])
        today = datetime.date.today()
        if os.environ['CURRENT_ACCOUNT_ID'] == '712098116579':
            message = 'AWS Billing & Cost Management Summary Report For OBP Prod Account(712098116579)'
            file_title = f'OBP AWS Cost Report Prod-{today}'
        elif os.environ['CURRENT_ACCOUNT_ID'] == '488499787904':
            message = 'AWS Billing & Cost Management Summary Report For OBP Non-Prod Account(488499787904)'
            file_title = f'OBP AWS Cost Report Non-Prod-{today}'
        if os.path.isfile(file):
            with open(file, 'rb') as fin:
                # contents = fin.read()
                res = self.slack.files.upload(fin, filetype=ftype, filename=basename,  channels=['obp-product-it', 'obp-pd', 'obp-fs-devs'], title=file_title, initial_comment=message)
                if res["ok"]:
                    print("File upload succeeded")
            if not res["ok"]:
                print("Post failed: %s" % res["error"])
                self.notify("File upload failed: %s.".format(res["error"]))  
        else:
            self.notify('{basename} not found. Uploading failed.')

    def getAccounts(self):
        current_account = boto3.client('sts').get_caller_identity()
        os.environ['CURRENT_ACCOUNT_ID'] = current_account['Account']
        accounts = { current_account['Account']: current_account }
        return accounts
    
    def addRiReport(self, Name='RICoverage', Savings=False, PaymentOption='PARTIAL_UPFRONT', Service='Amazon Elastic Compute Cloud - Compute'): #Call with Savings True to get Utilization report in dollar savings
        type = 'chart' #other option table
        if Name == "RICoverage":
            results = []
            response = self.client.get_reservation_coverage(
                TimePeriod={
                    'Start': self.ristart.isoformat(),
                    'End': self.riend.isoformat()
                },
                Granularity='MONTHLY'
            )
            results.extend(response['CoveragesByTime'])
            while 'nextToken' in response:
                nextToken = response['nextToken']
                response = self.client.get_reservation_coverage(
                    TimePeriod={
                        'Start': self.ristart.isoformat(),
                        'End': self.riend.isoformat()
                    },
                    Granularity='MONTHLY',
                    NextPageToken=nextToken
                )
                results.extend(response['CoveragesByTime'])
                if 'nextToken' in response:
                    nextToken = response['nextToken']
                else:
                    nextToken = False
            
            rows = []
            for v in results:
                row = {'date':v['TimePeriod']['Start']}
                row.update({'Coverage%':float(v['Total']['CoverageHours']['CoverageHoursPercentage'])})
                rows.append(row)  
                    
            df = pd.DataFrame(rows)
            df.set_index("date", inplace= True)
            df = df.fillna(0.0)
            df = df.T
        elif Name in ['RIUtilization','RIUtilizationSavings']:
            #Only Six month to support savings
            results = []
            response = self.client.get_reservation_utilization(
                TimePeriod={
                    'Start': self.sixmonth.isoformat(),
                    'End': self.riend.isoformat()
                },
                Granularity='MONTHLY'
            )
            results.extend(response['UtilizationsByTime'])
            while 'nextToken' in response:
                nextToken = response['nextToken']
                response = self.client.get_reservation_utilization(
                    TimePeriod={
                        'Start': self.sixmonth.isoformat(),
                        'End': self.riend.isoformat()
                    },
                    Granularity='MONTHLY',
                    NextPageToken=nextToken
                )
                results.extend(response['UtilizationsByTime'])
                if 'nextToken' in response:
                    nextToken = response['nextToken']
                else:
                    nextToken = False
            
            rows = []
            if results:
                for v in results:
                    row = {'date':v['TimePeriod']['Start']}
                    if Savings:
                        row.update({'Savings$':float(v['Total']['NetRISavings'])})
                    else:
                        row.update({'Utilization%':float(v['Total']['UtilizationPercentage'])})
                    rows.append(row)  
                        
                df = pd.DataFrame(rows)
                df.set_index("date", inplace= True)
                df = df.fillna(0.0)
                df = df.T
                type = 'chart'
            else:
                df = pd.DataFrame(rows)
                type = 'table' #Dont try chart empty result
        elif Name == 'RIRecommendation':
            results = []
            response = self.client.get_reservation_purchase_recommendation(
                #AccountId='string', May use for Linked view
                LookbackPeriodInDays='SIXTY_DAYS',
                TermInYears='ONE_YEAR',
                PaymentOption=PaymentOption,
                Service=Service
            )
            results.extend(response['Recommendations'])
            while 'nextToken' in response:
                nextToken = response['nextToken']
                response = self.client.get_reservation_purchase_recommendation(
                    #AccountId='string', May use for Linked view
                    LookbackPeriodInDays='SIXTY_DAYS',
                    TermInYears='ONE_YEAR',
                    PaymentOption=PaymentOption,
                    Service=Service,
                    NextPageToken=nextToken
                )
                results.extend(response['Recommendations'])
                if 'nextToken' in response:
                    nextToken = response['nextToken']
                else:
                    nextToken = False
                
            rows = []
            for i in results:
                for v in i['RecommendationDetails']:
                    row = v['InstanceDetails'][list(v['InstanceDetails'].keys())[0]]
                    row['Recommended']=v['RecommendedNumberOfInstancesToPurchase']
                    row['Minimum']=v['MinimumNumberOfInstancesUsedPerHour']
                    row['Maximum']=v['MaximumNumberOfInstancesUsedPerHour']
                    row['Savings']=v['EstimatedMonthlySavingsAmount']
                    row['OnDemand']=v['EstimatedMonthlyOnDemandCost']
                    row['BreakEvenIn']=v['EstimatedBreakEvenInMonths']
                    row['UpfrontCost']=v['UpfrontCost']
                    row['MonthlyCost']=v['RecurringStandardMonthlyCost']
                    rows.append(row)  
                
                    
            df = pd.DataFrame(rows)
            df = df.fillna(0.0)
            type = 'table' #Dont try chart this
        self.reports.append({'Name':Name,'Data':df, 'Type':type})
            
    def addLinkedReports(self, Name='RI_{}',PaymentOption='PARTIAL_UPFRONT'):
        pass
            
    def addReport(self, Name="Default",GroupBy=[{"Type": "DIMENSION","Key": "SERVICE"},], 
    Style='Total', NoCredits=True, CreditsOnly=False, RefundOnly=False, UpfrontOnly=False, IncSupport=False):
        type = 'chart' #other option table
        results = []
        if not NoCredits:
            response = self.client.get_cost_and_usage(
                TimePeriod={
                    'Start': self.start.isoformat(),
                    'End': self.end.isoformat()
                },
                Granularity='MONTHLY',
                Metrics=[
                    'UnblendedCost',
                ],
                GroupBy=GroupBy
            )
        else:
            Filter = {"And": []}

            Dimensions={"Not": {"Dimensions": {"Key": "RECORD_TYPE","Values": ["Credit", "Refund", "Upfront", "Support"]}}}
            if INC_SUPPORT or IncSupport: #If global set for including support, we dont exclude it
                Dimensions={"Not": {"Dimensions": {"Key": "RECORD_TYPE","Values": ["Credit", "Refund", "Upfront"]}}}
            if CreditsOnly:
                Dimensions={"Dimensions": {"Key": "RECORD_TYPE","Values": ["Credit",]}}
            if RefundOnly:
                Dimensions={"Dimensions": {"Key": "RECORD_TYPE","Values": ["Refund",]}}
            if UpfrontOnly:
                Dimensions={"Dimensions": {"Key": "RECORD_TYPE","Values": ["Upfront",]}}

            tagValues = None
            if TAG_KEY:
                tagValues = self.client.get_tags(
                    SearchString=TAG_VALUE_FILTER,
                    TimePeriod = {
                        'Start': self.start.isoformat(),
                        'End': datetime.date.today().isoformat()
                    },
                    TagKey=TAG_KEY
                )

            if tagValues:
                Filter["And"].append(Dimensions)
                if len(tagValues["Tags"]) > 0:
                    Tags = {"Tags": {"Key": TAG_KEY, "Values": tagValues["Tags"]}}
                    Filter["And"].append(Tags)
            else:
                Filter = Dimensions.copy()

            response = self.client.get_cost_and_usage(
                TimePeriod={
                    'Start': self.start.isoformat(),
                    'End': self.end.isoformat()
                },
                Granularity='MONTHLY',
                Metrics=[
                    'UnblendedCost',
                ],
                GroupBy=GroupBy,
                Filter=Filter
            )

        if response:
            results.extend(response['ResultsByTime'])
     
            while 'nextToken' in response:
                nextToken = response['nextToken']
                response = self.client.get_cost_and_usage(
                    TimePeriod={
                        'Start': self.start.isoformat(),
                        'End': self.end.isoformat()
                    },
                    Granularity='MONTHLY',
                    Metrics=[
                        'UnblendedCost',
                    ],
                    GroupBy=GroupBy,
                    NextPageToken=nextToken
                )
     
                results.extend(response['ResultsByTime'])
                if 'nextToken' in response:
                    nextToken = response['nextToken']
                else:
                    nextToken = False
        rows = []
        sort = ''
        for v in results:
            row = {'date':v['TimePeriod']['Start']}
            sort = v['TimePeriod']['Start']
            for i in v['Groups']:
                key = i['Keys'][0]
                if key in self.accounts:
                    key = self.accounts[key]['Account']
                row.update({key:float(i['Metrics']['UnblendedCost']['Amount'])}) 
            if not v['Groups']:
                row.update({'Total':float(v['Total']['UnblendedCost']['Amount'])})
            rows.append(row)  

        df = pd.DataFrame(rows)
        df.set_index("date", inplace= True)
        df = df.fillna(0.0)
        
        if Style == 'Change':
            dfc = df.copy()
            lastindex = None
            for index, row in df.iterrows():
                if lastindex:
                    for i in row.index:
                        try:
                            df.at[index,i] = dfc.at[index,i] - dfc.at[lastindex,i]
                        except:
                            logging.exception("Error")
                            df.at[index,i] = 0
                lastindex = index
        df = df.T
        df = df.sort_values(sort, ascending=False)
        self.reports.append({'Name':Name,'Data':df, 'Type':type})
                
    def generateExcel(self):
        # Create a Pandas Excel writer using XlsxWriter as the engine.\
        os.chdir('/tmp')
        today = datetime.date.today()
        if os.environ['CURRENT_ACCOUNT_ID'] == '712098116579':
            file_name = f'obp_cost_explorer_report_prod_{today}.xlsx'
        elif os.environ['CURRENT_ACCOUNT_ID'] == '488499787904':
            file_name = f'obp_cost_explorer_report_non_prod_{today}.xlsx'
        os.environ['SLACK_FILE_NAME'] = file_name
        writer = pd.ExcelWriter(file_name, engine='xlsxwriter')
        workbook = writer.book
        for report in self.reports:
            print(report['Name'],report['Type'])
            report['Data'].to_excel(writer, sheet_name=report['Name'])
            worksheet = writer.sheets[report['Name']]
            if report['Type'] == 'chart':
                
                # Create a chart object.
                chart = workbook.add_chart({'type': 'column', 'subtype': 'stacked'})
                chartend=12
                if CURRENT_MONTH:
                    chartend=13
                for row_num in range(1, len(report['Data']) + 1):
                    chart.add_series({
                        'name':       [report['Name'], row_num, 0],
                        'categories': [report['Name'], 0, 1, 0, chartend],
                        'values':     [report['Name'], row_num, 1, row_num, chartend],
                    })
                chart.set_y_axis({'label_position': 'low'})
                chart.set_x_axis({'label_position': 'low'})
                worksheet.insert_chart('O2', chart, {'x_scale': 2.0, 'y_scale': 2.0})
        writer.save()

def main_handler(event=None, context=None): 
    costexplorer = CostExplorer(CurrentMonth=False)
    #Default addReport has filter to remove Support / Credits / Refunds / UpfrontRI
    #Overall Billing Reports
    costexplorer.addReport(Name="Total", GroupBy=[],Style='Total',IncSupport=True)
    costexplorer.addReport(Name="TotalChange", GroupBy=[],Style='Change')
    costexplorer.addReport(Name="TotalInclCredits", GroupBy=[],Style='Total',NoCredits=False,IncSupport=True)
    costexplorer.addReport(Name="TotalInclCreditsChange", GroupBy=[],Style='Change',NoCredits=False)
    costexplorer.addReport(Name="Credits", GroupBy=[],Style='Total',CreditsOnly=True)
    costexplorer.addReport(Name="Refunds", GroupBy=[],Style='Total',RefundOnly=True)
    costexplorer.addReport(Name="RIUpfront", GroupBy=[],Style='Total',UpfrontOnly=True)
    #GroupBy Reports
    costexplorer.addReport(Name="Services", GroupBy=[{"Type": "DIMENSION","Key": "SERVICE"}],Style='Total',IncSupport=True)
    costexplorer.addReport(Name="ServicesChange", GroupBy=[{"Type": "DIMENSION","Key": "SERVICE"}],Style='Change')
    costexplorer.addReport(Name="Accounts", GroupBy=[{"Type": "DIMENSION","Key": "LINKED_ACCOUNT"}],Style='Total')
    costexplorer.addReport(Name="AccountsChange", GroupBy=[{"Type": "DIMENSION","Key": "LINKED_ACCOUNT"}],Style='Change')
    costexplorer.addReport(Name="Regions", GroupBy=[{"Type": "DIMENSION","Key": "REGION"}],Style='Total')
    costexplorer.addReport(Name="RegionsChange", GroupBy=[{"Type": "DIMENSION","Key": "REGION"}],Style='Change')
    if os.environ.get('COST_TAGS'): #Support for multiple/different Cost Allocation tags
        for tagkey in os.environ.get('COST_TAGS').split(','):
            tabname = tagkey.replace(":",".") #Remove special chars from Excel tabname
            costexplorer.addReport(Name="{}".format(tabname)[:31], GroupBy=[{"Type": "TAG","Key": tagkey}],Style='Total')
            costexplorer.addReport(Name="Change-{}".format(tabname)[:31], GroupBy=[{"Type": "TAG","Key": tagkey}],Style='Change')
    #RI Reports
    costexplorer.addRiReport(Name="RICoverage")
    costexplorer.addRiReport(Name="RIUtilization")
    costexplorer.addRiReport(Name="RIUtilizationSavings", Savings=True)
    costexplorer.addRiReport(Name="RIRecommendation") #Service supported value(s): Amazon Elastic Compute Cloud - Compute, Amazon Relational Database Service
    costexplorer.generateExcel()
    slack_file_name = os.environ['SLACK_FILE_NAME']
    costexplorer.upload_to_slack(f"/tmp/{slack_file_name}", "xlsx")
    return "Report Generated"

if __name__ == '__main__':
    main_handler()