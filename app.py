
# Setup storage account key etc
import os
from os import environ

storage_account_name = "svvpocdlgen2"
storage_account_access_key = environ.get("AZURE_STORAGE_ACCESS_KEY").strip()


# Read all files in blob container
from azure.storage.blob import BlockBlobService

block_blob_service = BlockBlobService(account_name=storage_account_name, account_key=storage_account_access_key)
generator = block_blob_service.list_blobs('friksjonosmaalingervictortest')
filenames = []
processed = []

for blob in generator:
    if blob.name.startswith("processed_"):
        processed.append( blob.name.replace("processed_", "") )
    elif blob.name.endswith(".csv"):
        filenames.append(blob.name)

# delete the files that has already been processed
for p in processed:
    if p in filenames:
        filenames.remove(p)

print("Already processed:")
for name in processed:
    print(name)
    
print("Not processed:")
for name in filenames:
    print(name)

# If there is nothing to process. Exit.
import sys
if not filenames:
    print("Nothing new to process... Exiting....")
    sys.exit()

# Create spark
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName('vinter-prep-wrangler').config("spark.hadoop.fs.wasbs.impl", "org.apache.hadoop.fs.azure.NativeAzureFileSystem").config("fs.wasbs.impl", "org.apache.hadoop.fs.azure.NativeAzureFileSystem").config("fs.azure.account.key."+storage_account_name+".blob.core.windows.net", storage_account_access_key).getOrCreate()


# DB Setup
jdbcHostname = environ.get("AZURE_SQL_HOST")
jdbcDatabase = environ.get("AZURE_SQL_DB")
jdbcPort = environ.get("AZURE_SQL_PORT")
username = environ.get("AZURE_SQL_UNAME")
password = environ.get("AZURE_SQL_PASSWD").strip()

jdbcUrl = "jdbc:sqlserver://{0}:{1};database={2}".format(jdbcHostname, jdbcPort, jdbcDatabase)
connectionProperties = {
  "user" : username,
  "password" : password,
  "driver" : "com.microsoft.sqlserver.jdbc.SQLServerDriver"
}

import pandas as pd
import utm
from geopy import distance

def getlatlong(row):
    tup = utm.to_latlon(row.iloc[0], row.iloc[1], 33, 'U')
    return pd.Series(tup[:2])

# Read CSV and writo to DB
for file in filenames:
    print("Processing file: " + file)
    df = spark.read.format("csv").options(header='true',inferschema='true',sep=",").load("wasbs://friksjonosmaalingervictortest@svvpocdlgen2.blob.core.windows.net/" + file)
    print(file + " has " + str(df.count()) + " rows.")
    
    df = df.toPandas()
    df = df[(df[['Latitude']] != 0).all(axis=1)]
    df[['Longitude', 'Latitude']] = df[['Longitude', 'Latitude']].apply(getlatlong, axis=1)
    df['distancekm'] = df.apply(lambda x: distance.distance((x['startlat'], x['startlong']) , (x['endlat'], x['endlon'])).km, axis = 1)
    df2 = spark.createDataFrame(df)

    # write to db
    df2.write.jdbc(url=jdbcUrl, table="friksjondataOpenshift", mode="append", properties=connectionProperties)
    # Write dummy file
    block_blob_service.create_blob_from_text('friksjonosmaalingervictortest', "processed_" + file, 'dummy')
    





# Stop spark
spark.stop()

